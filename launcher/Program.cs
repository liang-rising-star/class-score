using System.Diagnostics;

namespace ClassScore.Launcher;

/// <summary>
/// 安装目录根部的启动器：
///   class-score\
///     class-score.exe          ← 本程序，双击即启动
///     desktop\                 ← 桌面程序本体与 .NET 依赖
///     class-score-system\      ← 后端（Python 运行时、模板、数据）
/// 只负责把 desktop 里的主程序拉起来，然后自己退出，
/// 这样任务管理器里看到的仍然是 class-score（主程序同一进程名）。
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        var baseDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        var core = Path.Combine(baseDir, "desktop", "class-score.exe");

        if (!File.Exists(core))
        {
            MessageBox.Show(
                "找不到主程序：\n" + core +
                "\n\n请确认 desktop 文件夹没有丢失或被杀毒软件隔离。",
                "class-score", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        var startInfo = new ProcessStartInfo(core)
        {
            UseShellExecute = false,
            WorkingDirectory = Path.Combine(baseDir, "desktop")
        };

        // 把安装目录作为根目录传给主程序，避免它向上乱找
        var forwarded = new List<string>();
        for (var i = 0; i < args.Length; i++)
        {
            forwarded.Add(args[i]);
            if (args[i] is "--root" or "-r") i++;      // 用户已显式指定，保留原值
        }

        if (!forwarded.Contains("--root") && !forwarded.Contains("-r"))
        {
            forwarded.Insert(0, "--root");
            forwarded.Insert(1, baseDir);
        }

        foreach (var arg in forwarded)
        {
            startInfo.ArgumentList.Add(arg);
        }

        try
        {
            Process.Start(startInfo);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, "class-score",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
