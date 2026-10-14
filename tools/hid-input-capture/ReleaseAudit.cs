using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Reflection;
using System.Reflection.Emit;
using System.Security.Cryptography;
using System.Text;

internal static class ReleaseAudit
{
    internal static object Check(string dllPath, string pdbPath, string sourcePath)
    {
        using var dll = File.OpenRead(dllPath);
        string dllHash = Convert.ToHexString(SHA256.HashData(dll));
        dll.Position = 0;
        using var pe = new PEReader(dll);
        var debug = pe.ReadDebugDirectory().Single(e => e.Type == DebugDirectoryEntryType.CodeView);
        var codeView = pe.ReadCodeViewDebugDirectoryData(debug);
        using var pdb = File.OpenRead(pdbPath);
        using var provider = MetadataReaderProvider.FromPortablePdbStream(pdb);
        var reader = provider.GetMetadataReader();
        var id = reader.DebugMetadataHeader!.Id.ToArray();
        bool pdbMatches = new Guid(id.AsSpan(0, 16)) == codeView.Guid;
        var document = reader.Documents.Select(reader.GetDocument).Single(d =>
            Path.GetFileName(reader.GetString(d.Name)) == "HidConnection.cs");
        if (reader.GetGuid(document.HashAlgorithm) != new Guid("8829d00f-11b8-4213-878b-770e8597ac16"))
            throw new InvalidDataException("Expected SHA-256 PDB source checksum.");
        byte[] expected = reader.GetBlobBytes(document.Hash);
        byte[] source = File.ReadAllBytes(sourcePath);
        string normalization = "exact bytes";
        if (!SHA256.HashData(source).SequenceEqual(expected))
        {
            source = Encoding.UTF8.GetBytes(File.ReadAllText(sourcePath).Replace("\r\n", "\n"));
            normalization = "LF source variant";
            if (!SHA256.HashData(source).SequenceEqual(expected)) normalization = "source differs";
        }
        var methods = TransportMethods(pe);
        var instructions = methods.Values.SelectMany(x => x).ToArray();
        bool hasRead = instructions.Any(x => x.Contains("::Read") || x.Contains("::GetInputReport"));
        bool hasWrite = instructions.Any(x => x.Contains("::WriteAsync"));
        if (hasRead || !hasWrite || methods.Count < 4)
            throw new InvalidDataException("Unexpected installed HID transport implementation; inspect before capture.");
        return new { dll_sha256 = dllHash, pdb_matches_dll = pdbMatches,
            pdb_source_sha256 = Convert.ToHexString(expected), pdb_source_match = normalization,
            source_provenance_established = pdbMatches && normalization != "source differs",
            transport_read_call_found = hasRead, transport_write_call_found = hasWrite, methods,
            scope = "Static IL of the installed transport; stale PDB does not establish source provenance" };
    }

    private static Dictionary<string, string[]> TransportMethods(PEReader pe)
    {
        var metadata = pe.GetMetadataReader();
        var opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
            .ToDictionary(o => unchecked((ushort)o.Value));
        string TypeName(TypeDefinitionHandle h)
        {
            var t = metadata.GetTypeDefinition(h);
            return t.GetDeclaringType().IsNil ? metadata.GetString(t.Namespace) + "." + metadata.GetString(t.Name)
                : TypeName(t.GetDeclaringType()) + "/" + metadata.GetString(t.Name);
        }
        string Resolve(EntityHandle h) => h.Kind switch
        {
            HandleKind.TypeDefinition => TypeName((TypeDefinitionHandle)h),
            HandleKind.TypeReference => metadata.GetString(metadata.GetTypeReference((TypeReferenceHandle)h).Namespace)
                + "." + metadata.GetString(metadata.GetTypeReference((TypeReferenceHandle)h).Name),
            HandleKind.MethodDefinition => TypeName(metadata.GetMethodDefinition((MethodDefinitionHandle)h).GetDeclaringType())
                + "::" + metadata.GetString(metadata.GetMethodDefinition((MethodDefinitionHandle)h).Name),
            HandleKind.MemberReference => Resolve(metadata.GetMemberReference((MemberReferenceHandle)h).Parent)
                + "::" + metadata.GetString(metadata.GetMemberReference((MemberReferenceHandle)h).Name),
            HandleKind.MethodSpecification => Resolve(metadata.GetMethodSpecification((MethodSpecificationHandle)h).Method),
            _ => h.Kind.ToString()
        };
        var methods = new Dictionary<string, string[]>();
        foreach (var handle in metadata.MethodDefinitions)
        {
            var method = metadata.GetMethodDefinition(handle);
            string type = TypeName(method.GetDeclaringType());
            if (!(type == "IMouse2.Kernel.HidConnection" || type.StartsWith("IMouse2.Kernel.HidConnection/"))
                || method.RelativeVirtualAddress == 0) continue;
            var code = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!;
            var lines = new List<string>();
            for (int i = 0; i < code.Length;)
            {
                ushort value = code[i++];
                if (value == 0xfe) value = (ushort)(0xfe00 | code[i++]);
                var op = opcodes[value];
                string operand;
                if (op.OperandType is OperandType.InlineMethod or OperandType.InlineType or OperandType.InlineTok)
                {
                    operand = Resolve(MetadataTokens.EntityHandle(BitConverter.ToInt32(code, i))); i += 4;
                }
                else
                {
                    int count = op.OperandType switch
                    {
                        OperandType.InlineNone => 0,
                        OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                        OperandType.InlineVar => 2,
                        OperandType.InlineI8 or OperandType.InlineR => 8,
                        OperandType.InlineSwitch => 4 + 4 * BitConverter.ToInt32(code, i), _ => 4
                    };
                    operand = Convert.ToHexString(code.AsSpan(i, count)); i += count;
                }
                lines.Add(op.Name + " " + operand);
            }
            methods[type + "::" + metadata.GetString(method.Name)] = lines.ToArray();
        }
        return methods;
    }
}
