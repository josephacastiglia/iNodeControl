using System.ComponentModel;
using System.Windows;
using System.Windows.Media;

namespace IMouse2;

/// <summary>
/// One phone on the wall beside the master view. These exist so an operator running a rack
/// can see at a glance whether a mirrored action actually landed everywhere - which is the
/// whole reason the wall exists, so a tile that has stopped updating must look different
/// from one that is merely showing a still screen.
/// </summary>
public sealed class Thumb : INotifyPropertyChanged
{
    public string Id { get; init; } = "";

    private string _name = "";
    public string Name
    {
        get => _name;
        set { if (_name != value) { _name = value; Notify(nameof(Name)); Notify(nameof(ShortName)); Notify(nameof(Detail)); } }
    }

    /// <summary>
    /// What actually fits under a thumbnail. A tile is only as wide as a phone screen at
    /// the chosen size - about 55 pixels at the default - and the default name for an
    /// unnamed phone is "iPhone XR - 35:8D", of which only the last part distinguishes it
    /// from its neighbours. Trimming from the right would throw away the only useful half.
    ///
    /// The alternative, letting the tile grow to fit its caption, is what made the wall
    /// jitter: a caption of changing width resizes the tile and reflows the whole wall.
    /// A phone the operator has named in iMouse keeps that name, which is the point of
    /// naming it.
    /// </summary>
    public string ShortName
    {
        get
        {
            int at = _name.LastIndexOf('\u00b7');
            return at >= 0 && at + 1 < _name.Length ? _name[(at + 1)..].Trim() : _name;
        }
    }

    /// <summary>Full name and state, for the tooltip - where there is room for it.</summary>
    public string Detail => (_status.Length == 0 ? _name : _name + "  \u2014  " + _status)
        + "  \u2014  " + _delivery.Detail;

    private TileStatusView _delivery = TileStatusView.From(null, true, false);
    public string DeliveryLabel => _delivery.Label;
    public bool DeliveryWarning => _delivery.Warning;
    public void SetDelivery(TileStatusView value)
    {
        if (_delivery == value) return;
        _delivery = value;
        Notify(nameof(DeliveryLabel)); Notify(nameof(DeliveryWarning)); Notify(nameof(Detail));
    }

    private ImageSource? _image;
    // Reference comparison, deliberately: this is assigned the same WriteableBitmap on
    // every frame, and without the guard each one raised a binding update that had nothing
    // to say. ImageSource does not overload equality, so != is already a reference test.
    public ImageSource? Image { get => _image; set { if (!ReferenceEquals(_image, value)) { _image = value; Notify(nameof(Image)); } } }

    /// <summary>
    /// Bitmap updates per second after pixel deduplication, not received source frames. Shown because the wall's whole
    /// job is to answer "is this phone keeping up", and a phone whose own mirror stream is
    /// slow looks identical to a console that has stopped drawing it. Measured on this
    /// rack: two identical iPhone XRs under the same mirrored swipe produced 27.5 and 4.5
    /// new frames a second, so the difference is real and worth showing.
    /// </summary>
    ///
    /// Reported as a whole number, and only when it moves by a full frame a second. A rate
    /// twitching between 20.7 and 21.1 is noise: it pulls the eye to a number that is not
    /// telling the operator anything new.
    private double _fps;
    public double Fps
    {
        get => _fps;
        set
        {
            double next = value <= 0 ? 0 : Math.Round(value);
            if (next == _fps || (next != 0 && _fps != 0 && Math.Abs(_fps - next) < 1)) return;
            _fps = next; Notify(nameof(Fps)); Notify(nameof(RateText)); Notify(nameof(RateVisibility));
        }
    }
    public string RateText => _fps <= 0 ? "" : $"{_fps:0}/s";
    public Visibility RateVisibility => _fps <= 0 ? Visibility.Collapsed : Visibility.Visible;

    private string _status = "";
    public string Status
    {
        get => _status;
        set { if (_status != value) { _status = value; Notify(nameof(Status)); Notify(nameof(Detail)); } }
    }

    /// <summary>True when this phone is currently receiving the master's mirrored actions.</summary>
    private bool _following;
    public bool Following { get => _following; set { if (_following != value) { _following = value; Notify(nameof(Following)); } } }

    /// <summary>True when the phone is mirroring and controllable, so its tile should look live.</summary>
    private bool _ready;
    public bool Ready { get => _ready; set { if (_ready != value) { _ready = value; Notify(nameof(Ready)); } } }

    private void Notify(string p) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(p));
    public event PropertyChangedEventHandler? PropertyChanged;
}
