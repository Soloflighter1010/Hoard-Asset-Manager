// What this project imported through Hoard, kept in ProjectSettings/Hoard/imports.json so it travels with the
// project (and with version control). One entry per import: which product, which file, and when.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace SoloFlighter.Hoard.Editor
{
    public static class ImportLog
    {
        static readonly string LogFile = Path.Combine("ProjectSettings", "Hoard", "imports.json");

        public sealed class Entry
        {
            public string Store, Name, Creator, File, ImportedAt;
        }

        public static List<Entry> Read()
        {
            var list = new List<Entry>();
            try
            {
                if (!System.IO.File.Exists(LogFile) || new FileInfo(LogFile).Length > 16L * 1024 * 1024) return list;
                var doc = Json.Parse(System.IO.File.ReadAllText(LogFile, Encoding.UTF8));
                var items = doc.Get("imports");
                if (items == null || items.Kind != JsonKind.Array) return list;
                foreach (var v in items.Items)
                    if (v.Kind == JsonKind.Object)
                        list.Add(new Entry { Store = v.Str("store"), Name = v.Str("name"), Creator = v.Str("creator"),
                                             File = v.Str("file"), ImportedAt = v.Str("imported_at") });
            }
            catch (Exception) { /* unreadable: start a new log rather than lose the project's work */ }
            return list;
        }

        public static void Record(HoardAsset asset, string file)
        {
            var list = Read();
            list.Add(new Entry { Store = asset.Store, Name = asset.Name, Creator = asset.Creator, File = file,
                                 ImportedAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") });
            var sb = new StringBuilder("{\n  \"format\": \"hoard-unity-imports\",\n  \"version\": 1,\n  \"imports\": [\n");
            for (int n = 0; n < list.Count; n++)
            {
                var e = list[n];
                sb.Append("    {\"store\": ").Append(Q(e.Store)).Append(", \"name\": ").Append(Q(e.Name))
                  .Append(", \"creator\": ").Append(Q(e.Creator)).Append(", \"file\": ").Append(Q(e.File))
                  .Append(", \"imported_at\": ").Append(Q(e.ImportedAt)).Append(n < list.Count - 1 ? "},\n" : "}\n");
            }
            sb.Append("  ]\n}\n");
            Directory.CreateDirectory(Path.GetDirectoryName(LogFile));
            string temp = LogFile + ".tmp";
            System.IO.File.WriteAllText(temp, sb.ToString(), new UTF8Encoding(false));
            if (System.IO.File.Exists(LogFile)) System.IO.File.Replace(temp, LogFile, null);
            else System.IO.File.Move(temp, LogFile);
        }

        public static bool Imported(HoardAsset asset, List<Entry> log)
        {
            return log.Exists(e => e.Store == asset.Store && e.Name == asset.Name);
        }

        static string Q(string s)
        {
            if (s == null) return "null";
            return Encoding.UTF8.GetString(Json.Canonical(new JsonValue { Kind = JsonKind.String, Text = s }));
        }
    }
}
