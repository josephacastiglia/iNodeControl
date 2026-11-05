using System.Net;
using System.Net.Sockets;
using System.Text;

namespace IMouse2.Kernel;

/// <summary>Withdraws a stopped receiver's AirPlay name from the network.</summary>
public interface IReceiverWithdrawal
{
    /// <summary>Returns the IPv4 interfaces the goodbye went out on. Throws if none could be sent.</summary>
    IReadOnlyList<string> Withdraw(ReceiverConfig receiver);
}

/// <summary>
/// The kernel ends UxPlay by killing it, so the receiver's own mDNS responder never sends its
/// goodbye and every phone keeps listing the name for the record lifetime (4500 s). This sends the
/// goodbye on its behalf, byte for byte as tools/mdns_goodbye.py does: the _airplay._tcp and
/// _raop._tcp PTR records with TTL 0 (RFC 6762 section 10.1), from port 5353, on every IPv4
/// interface, three times one second apart. Call only after the receiver's exit is confirmed.
/// </summary>
public sealed class MdnsGoodbye : IReceiverWithdrawal
{
    private static readonly IPEndPoint Group = new(IPAddress.Parse("224.0.0.251"), 5353);
    private readonly int _repeats;
    private readonly TimeSpan _gap;

    public MdnsGoodbye(int repeats = 3, TimeSpan? gap = null)
    {
        if (repeats is < 1 or > 10) throw new ArgumentOutOfRangeException(nameof(repeats));
        _repeats = repeats; _gap = gap ?? TimeSpan.FromSeconds(1);
    }

    internal static byte[] Name(string name)
    {
        var output = new List<byte>();
        foreach (var label in name.TrimEnd('.').Split('.'))
        {
            var raw = Encoding.UTF8.GetBytes(label);
            if (raw.Length is 0 or > 63) throw new ArgumentException("Bad DNS label in " + name);
            output.Add((byte)raw.Length); output.AddRange(raw);
        }
        output.Add(0);
        return [.. output];
    }

    private static void BigEndian(List<byte> output, int value, int bytes)
    {
        for (int shift = (bytes - 1) * 8; shift >= 0; shift -= 8) output.Add((byte)(value >> shift));
    }

    private static void Ptr(List<byte> output, string owner, string target)
    {
        var data = Name(target);
        output.AddRange(Name(owner));
        BigEndian(output, 12, 2);   // PTR
        BigEndian(output, 1, 2);    // IN, no cache-flush bit on shared records
        BigEndian(output, 0, 4);    // TTL 0: goodbye
        BigEndian(output, data.Length, 2);
        output.AddRange(data);
    }

    internal static byte[] Packet(ReceiverConfig receiver)
    {
        var mac = receiver.Mac.Replace(":", "").ToUpperInvariant();
        var output = new List<byte>();
        BigEndian(output, 0, 2); BigEndian(output, 0x8400, 2);   // id 0, authoritative response
        BigEndian(output, 0, 2); BigEndian(output, 2, 2);        // no questions, two answers
        BigEndian(output, 0, 4);
        Ptr(output, "_airplay._tcp.local", receiver.Name + "._airplay._tcp.local");
        Ptr(output, "_raop._tcp.local", mac + "@" + receiver.Name + "._raop._tcp.local");
        return [.. output];
    }

    internal static IReadOnlyList<IPAddress> Interfaces() =>
        Dns.GetHostAddresses(Dns.GetHostName())
            .Where(a => a.AddressFamily == AddressFamily.InterNetwork)
            .Where(a => !a.ToString().StartsWith("127.") && !a.ToString().StartsWith("169.254."))
            .Distinct().OrderBy(a => a.ToString(), StringComparer.Ordinal).ToArray();

    public IReadOnlyList<string> Withdraw(ReceiverConfig receiver)
    {
        var packet = Packet(receiver);
        var interfaces = Interfaces();
        if (interfaces.Count == 0) throw new IOException("No IPv4 interface to send the AirPlay goodbye on.");
        using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
        // Listeners ignore mDNS responses not sent from port 5353 (RFC 6762 section 11); share it.
        socket.ExclusiveAddressUse = false;
        socket.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
        socket.Bind(new IPEndPoint(IPAddress.Any, 5353));
        socket.SetSocketOption(SocketOptionLevel.IP, SocketOptionName.MulticastTimeToLive, 255);
        int sent = 0;
        for (int attempt = 0; attempt < _repeats; attempt++)
        {
            foreach (var address in interfaces)
            {
                try
                {
                    socket.SetSocketOption(SocketOptionLevel.IP, SocketOptionName.MulticastInterface, address.GetAddressBytes());
                    socket.SendTo(packet, Group);
                    sent++;
                }
                catch (SocketException ex) { Console.WriteLine("AirPlay goodbye on " + address + " failed: " + ex.Message); }
            }
            if (attempt + 1 < _repeats) Thread.Sleep(_gap);
        }
        if (sent == 0) throw new IOException("The AirPlay goodbye could not be sent on any interface.");
        return interfaces.Select(a => a.ToString()).ToArray();
    }
}
