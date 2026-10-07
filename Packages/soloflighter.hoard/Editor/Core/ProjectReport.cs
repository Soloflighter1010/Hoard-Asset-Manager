// What this project uses, for Hoard's Projects view (Hoard's issue #86): written by the window into Hoard's own
// app-data folder (projects/<id>.json), never into your downloads. Hoard reads it to list each project's assets, show
// which of them have updates, and make the credits list there too. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SoloFlighter.Hoard
{
    public sealed class ProjectAsset
    {
        public string Store, Name, Creator, Folder, Url;
        public string Status;   // "yes": a package of it is all in the project; "partly"; "imported": only the import log says so
    }

    public static class ProjectReport
    {
        public const int MaxAssets = 5000;

        /// <summary>The report's file for a project: projects/ in Hoard's folder, named for the project's full path, so
        /// each project has one, and opening it again replaces it.</summary>
        public static string FileFor(string dataDir, string projectPath)
        {
            string full = Path.GetFullPath(projectPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(full));
                var id = new StringBuilder();
                for (int i = 0; i < 8; i++) id.Append(hash[i].ToString("x2"));
                return Path.Combine(dataDir, "projects", id + ".json");
            }
        }

        /// <summary>The report, as canonical JSON.</summary>
        public static byte[] Build(string projectPath, string name, string unityVersion, string updated,
                                   List<ProjectAsset> assets, CreditsFile credits)
        {
            return Json.Canonical(Tree(projectPath, name, unityVersion, updated, assets, credits));
        }

        /// <summary>The report, and the same report saying when it was written: whether it changed is told from the
        /// first (the time always differs), and the second is what's written. Built once.</summary>
        public static byte[] Build(string projectPath, string name, string unityVersion, List<ProjectAsset> assets,
                                   CreditsFile credits, string updated, out byte[] stamped)
        {
            var root = Tree(projectPath, name, unityVersion, "", assets, credits);
            byte[] plain = Json.Canonical(root);
            root.Get("updated").Text = updated;
            stamped = Json.Canonical(root);
            return plain;
        }

        static JsonValue Tree(string projectPath, string name, string unityVersion, string updated,
                              List<ProjectAsset> assets, CreditsFile credits)
        {
            var root = Obj();
            Put(root, "format", Str("hoard-project"));
            Put(root, "version", Num(1));
            Put(root, "name", Str(Credits.OneLine(name, 200)));
            Put(root, "path", Str(Path.GetFullPath(projectPath)));
            Put(root, "unity", Str(Credits.OneLine(unityVersion, 40)));
            Put(root, "updated", Str(updated));
            var list = new List<JsonValue>();
            foreach (var a in assets)
            {
                if (list.Count >= MaxAssets) break;
                var o = Obj();
                Put(o, "store", Str(a.Store ?? ""));
                Put(o, "name", Str(a.Name ?? ""));
                Put(o, "creator", Str(a.Creator ?? ""));
                Put(o, "folder", Str(a.Folder ?? ""));
                Put(o, "url", a.Url == null ? Null() : Str(a.Url));
                Put(o, "status", Str(a.Status ?? "yes"));
                list.Add(o);
            }
            Put(root, "assets", Arr(list));
            var c = Obj();
            Put(c, "title", Str(credits.Title ?? ""));
            Put(c, "style", Str(credits.Format.ToString()));
            var left = new List<string>(credits.LeftOut);
            left.Sort(StringComparer.Ordinal);
            Put(c, "left_out", Arr(left.ConvertAll(Str)));
            Put(c, "added", Arr(credits.Added.ConvertAll(e =>
            {
                var o = Obj();
                Put(o, "name", Str(e.Name ?? ""));
                Put(o, "creator", Str(e.Creator ?? ""));
                Put(o, "url", e.Url == null ? Null() : Str(e.Url));
                return o;
            })));
            Put(root, "credits", c);
            return root;
        }

        /// <summary>Write the report, unless it's the same as what's there (so Hoard isn't told of a change that isn't one).
        /// True when it was written.</summary>
        public static bool Write(string file, byte[] report)
        {
            if (File.Exists(file))
            {
                var old = File.ReadAllBytes(file);
                if (old.Length == report.Length && Same(old, report)) return false;
            }
            JsonBuild.WriteFile(file, report);
            return true;
        }

        static bool Same(byte[] a, byte[] b)
        {
            for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
            return true;
        }

        static JsonValue Obj() { return JsonBuild.Obj(); }
        static JsonValue Arr(List<JsonValue> items) { return JsonBuild.Arr(items); }
        static JsonValue Str(string s) { return JsonBuild.Str(s); }
        static JsonValue Num(int n) { return JsonBuild.Num(n); }
        static JsonValue Null() { return JsonBuild.Null(); }
        static void Put(JsonValue o, string k, JsonValue v) { JsonBuild.Put(o, k, v); }
    }
}
