using System.Drawing.Drawing2D;
using System.Drawing.Text;

namespace ClassScore.Desktop;

/// <summary>
/// 托盘右键菜单：不用系统 ContextMenuStrip，改成自绘的圆角弹窗，
/// 视觉和应用内的卡片/按钮保持一致（白底、12px 圆角、淡蓝悬停）。
/// </summary>
internal sealed class TrayMenu : Form
{
    private const int Radius = 12;
    private const int RowWidth = 208;

    private static readonly Color TextColor = Color.FromArgb(31, 41, 55);
    private static readonly Color MutedColor = Color.FromArgb(100, 116, 139);
    private static readonly Color Accent = Color.FromArgb(37, 99, 235);
    private static readonly Color AccentDark = Color.FromArgb(29, 78, 216);
    private static readonly Color HoverBg = Color.FromArgb(239, 244, 255);
    private static readonly Color BorderColor = Color.FromArgb(226, 232, 240);
    private static readonly Color Danger = Color.FromArgb(185, 28, 28);
    private static readonly Color DangerHoverBg = Color.FromArgb(254, 242, 242);
    private static readonly Color Separator = Color.FromArgb(241, 245, 249);

    private readonly List<Control> _rows = new();

    public event Action? OpenRequested;
    public event Action? RestartRequested;
    public event Action? ExitRequested;

    public TrayMenu()
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        StartPosition = FormStartPosition.Manual;
        TopMost = true;
        BackColor = Color.White;
        DoubleBuffered = true;
        Padding = new Padding(8, 8, 8, 8);
        AutoScaleMode = AutoScaleMode.None;
        KeyPreview = true;
        Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Regular, GraphicsUnit.Point);

        AddRow("打开主界面", "\uE80F", bold: true, accent: true, onClick: () => OpenRequested?.Invoke());
        AddRow("重启系统", "", onClick: () => RestartRequested?.Invoke());
        AddSeparator();
        AddRow("退出", "\uE7E8", danger: true, onClick: () => ExitRequested?.Invoke());

        LayoutRows();
    }

    private void AddRow(string text, string glyph, Action onClick,
                        bool bold = false, bool accent = false, bool danger = false)
    {
        var row = new MenuRow(text, glyph, bold, accent, danger)
        {
            Width = RowWidth,
            Height = 38,
            Cursor = Cursors.Hand
        };
        row.Clicked += () =>
        {
            onClick();
            Close();
        };
        _rows.Add(row);
    }

    private void AddSeparator()
    {
        var line = new SeparatorRow { Width = RowWidth, Height = 11 };
        _rows.Add(line);
    }

    private void LayoutRows()
    {
        var y = Padding.Top;
        foreach (var row in _rows)
        {
            row.Left = Padding.Left;
            row.Top = y;
            y += row.Height;
            Controls.Add(row);
        }

        Width = RowWidth + Padding.Horizontal + 2;
        Height = y + Padding.Bottom + 2;
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            cp.ClassStyle |= 0x00020000;   // CS_DROPSHADOW：无边框窗口也带系统投影
            return cp;
        }
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ApplyRoundedRegion();
    }

    private void ApplyRoundedRegion()
    {
        using var path = Rounded(new Rectangle(0, 0, Width, Height), Radius);
        var old = Region;
        Region = new Region(path);
        old?.Dispose();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var pen = new Pen(BorderColor);
        using var path = Rounded(new Rectangle(0, 0, Width - 1, Height - 1), Radius);
        e.Graphics.DrawPath(pen, path);
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape) Close();
        base.OnKeyDown(e);
    }

    protected override void OnDeactivate(EventArgs e)
    {
        base.OnDeactivate(e);
        Close();
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        base.OnFormClosed(e);
        foreach (var row in _rows) row.Dispose();
    }

    internal static GraphicsPath Rounded(Rectangle bounds, int radius)
    {
        var path = new GraphicsPath();
        var d = radius * 2;
        path.AddArc(bounds.X, bounds.Y, d, d, 180, 90);
        path.AddArc(bounds.Right - d, bounds.Y, d, d, 270, 90);
        path.AddArc(bounds.Right - d, bounds.Bottom - d, d, d, 0, 90);
        path.AddArc(bounds.X, bounds.Bottom - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }
}

/// <summary>单行菜单项：左图标 + 文字，悬停时淡色圆角底。</summary>
internal sealed class MenuRow : Control
{
    private static readonly Color TextColor = Color.FromArgb(31, 41, 55);
    private static readonly Color Accent = Color.FromArgb(30, 64, 175);
    private static readonly Color AccentIcon = Color.FromArgb(37, 99, 235);
    private static readonly Color Danger = Color.FromArgb(185, 28, 28);
    private static readonly Color IconColor = Color.FromArgb(100, 116, 139);
    private static readonly Color HoverBg = Color.FromArgb(239, 244, 255);
    private static readonly Color DangerHoverBg = Color.FromArgb(254, 242, 242);

    private readonly string _glyph;
    private readonly bool _bold;
    private readonly bool _accent;
    private readonly bool _danger;
    private bool _hover;

    public event Action? Clicked;

    public MenuRow(string text, string glyph, bool bold, bool accent, bool danger)
    {
        Text = text;
        _glyph = glyph;
        _bold = bold;
        _accent = accent;
        _danger = danger;

        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint
                 | ControlStyles.UserPaint | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
    }

    protected override void OnMouseEnter(EventArgs e)
    {
        _hover = true;
        Invalidate();
        base.OnMouseEnter(e);
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        _hover = false;
        Invalidate();
        base.OnMouseLeave(e);
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Left) Clicked?.Invoke();
        base.OnMouseUp(e);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

        if (_hover)
        {
            var rect = new Rectangle(3, 3, Width - 6, Height - 6);
            using var path = TrayMenu.Rounded(rect, 8);
            using var brush = new SolidBrush(_danger ? DangerHoverBg : HoverBg);
            g.FillPath(brush, path);
        }

        var iconColor = _danger ? Danger : (_accent ? AccentIcon : IconColor);
        using (var iconFont = new Font("Segoe MDL2 Assets", 10.5f, FontStyle.Regular, GraphicsUnit.Point))
        using (var iconBrush = new SolidBrush(iconColor))
        using (var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
        {
            g.DrawString(_glyph, iconFont, iconBrush, new RectangleF(12, 0, 20, Height), sf);
        }

        var textColor = _danger ? Danger : (_accent ? Accent : TextColor);
        using var font = new Font("Microsoft YaHei UI", 9.5f,
            _bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Point);
        using var textBrush = new SolidBrush(textColor);
        using var format = new StringFormat { Alignment = StringAlignment.Near, LineAlignment = StringAlignment.Center };
        g.DrawString(Text, font, textBrush, new RectangleF(40, 0, Width - 50, Height), format);
    }
}

/// <summary>菜单里的分隔线。</summary>
internal sealed class SeparatorRow : Control
{
    public SeparatorRow()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint
                 | ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        using var pen = new Pen(Color.FromArgb(232, 237, 245));
        var y = Height / 2;
        e.Graphics.DrawLine(pen, 12, y, Width - 12, y);
    }
}
