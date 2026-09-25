// Where Hoard keeps things, found the same way the Hoard app does. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace SoloFlighter.Hoard
{
    public static class HoardLocation
    {
        /// <summary>Hoard's private folder in this user account's app data (HOARD_DATA_DIR moves it, as in the app).</summary>
        public static string DataDir()
        {
            string over = Environment.GetEnvironmentVariable("HOARD_DATA_DIR");
            if (!string.IsNullOrEmpty(over)) return Path.GetFullPath(ExpandHome(over));
            string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                return Path.Combine(string.IsNullOrEmpty(local) ? Path.Combine(home, "AppData", "Local") : local, "Hoard");
            }
            if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                return Path.Combine(home, "Library", "Application Support", "Hoard");
            string xdg = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
            return Path.Combine(string.IsNullOrEmpty(xdg) ? Path.Combine(home, ".local", "share") : xdg, "Hoard");
        }

        public static string KeyFile() { return Path.Combine(DataDir(), "integrity.key"); }

        /// <summary>Every place this user account's Hoard keeps its sealing key: Hoard's own folder and, on Windows,
        /// the private copy of it that Windows keeps for Hoard run with Microsoft Store Python (Store apps' writes to
        /// AppData are redirected to their own folder, so that Hoard has a key of its own).</summary>
        public static List<string> KeyFiles()
        {
            return KeyFiles(DataDir(), Environment.GetEnvironmentVariable("LOCALAPPDATA"),
                            RuntimeInformation.IsOSPlatform(OSPlatform.Windows));
        }

        public static List<string> KeyFiles(string dataDir, string localAppData, bool windows)
        {
            var files = new List<string> { Path.Combine(dataDir, "integrity.key") };
            if (!windows || string.IsNullOrEmpty(localAppData)) return files;
            try
            {
                string packages = Path.Combine(localAppData, "Packages");
                if (Directory.Exists(packages))
                    foreach (string dir in Directory.GetDirectories(packages, "PythonSoftwareFoundation.Python.*"))
                    {
                        string key = Path.Combine(dir, "LocalCache", "Local", "Hoard", "integrity.key");
                        if (File.Exists(key)) files.Add(key);
                    }
            }
            catch (Exception) { /* can't look: the main key will do */ }
            return files;
        }

        /// <summary>The downloads folder: the one chosen in Hoard's Settings, or Hoard's default (Documents/Hoard).</summary>
        public static string DownloadsFolder()
        {
            string config = Path.Combine(DataDir(), "config.json");
            try
            {
                if (File.Exists(config) && new FileInfo(config).Length < 1024 * 1024)
                {
                    string root = Json.Parse(File.ReadAllText(config, Encoding.UTF8)).Str("root");
                    if (!string.IsNullOrWhiteSpace(root))
                    {
                        string expanded = ExpandHome(Environment.ExpandEnvironmentVariables(root.Trim()));
                        return Path.GetFullPath(Path.IsPathRooted(expanded) ? expanded : Path.Combine(DataDir(), expanded));
                    }
                }
            }
            catch (Exception) { /* unreadable settings: fall back to the default, as the app does */ }
            return Path.Combine(DocumentsDir(), "Hoard");
        }

        static string DocumentsDir()
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                return Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);   // OneDrive-aware, as the app
            string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string docs = Path.Combine(home, "Documents");
            return Directory.Exists(docs) ? docs : home;
        }

        static string ExpandHome(string path)
        {
            if (path == "~" || path.StartsWith("~/") || path.StartsWith("~\\"))
                return Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + path.Substring(1);
            return path;
        }
    }
}
