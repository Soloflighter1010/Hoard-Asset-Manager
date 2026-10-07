// What you've changed in a project's credits list (issue #51): entries written in by hand, ones left out, the title
// and the format. Kept in ProjectSettings/Hoard/credits.json, beside the import log, so it travels with the project.
// Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace SoloFlighter.Hoard
{
    public sealed class CreditsFile
    {
        public const int MaxAdded = 500;
        public string Title = "Assets used";
        public CreditFormat Format = CreditFormat.List;
        public List<CreditEntry> Added = new List<CreditEntry>();
        public HashSet<string> LeftOut = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>Read it, or a fresh one when it's missing, too big or unreadable (never throws).</summary>
        public static CreditsFile Load(string path)
        {
            var f = new CreditsFile();
            try
            {
                if (!File.Exists(path) || new FileInfo(path).Length > 4L * 1024 * 1024) return f;
                var doc = Json.Parse(File.ReadAllText(path, Encoding.UTF8));
                if (doc.Kind != JsonKind.Object || doc.Str("format") != "hoard-unity-credits") return f;
                var title = doc.Get("title");
                if (title != null && title.Kind == JsonKind.String) f.Title = Credits.OneLine(title.Text, 100);
                CreditFormat fmt;
                if (Enum.TryParse(doc.Str("style") ?? "", out fmt) && Enum.IsDefined(typeof(CreditFormat), fmt)) f.Format = fmt;
                foreach (string k in doc.Strings("left_out")) if (k.Length <= 400) f.LeftOut.Add(k);
                var added = doc.Get("added");
                if (added != null && added.Kind == JsonKind.Array)
                    foreach (var v in added.Items)
                    {
                        if (v.Kind != JsonKind.Object || f.Added.Count >= MaxAdded) continue;
                        var e = new CreditEntry { Name = Credits.OneLine(v.Str("name"), 300), Creator = Credits.OneLine(v.Str("creator"), 200),
                                                  Store = "", Added = true };
                        e.Url = Credits.Link(null, v.Str("url"), true);
                        if (e.Name.Length > 0) f.Added.Add(e);
                    }
            }
            catch (Exception) { /* unreadable: start again rather than lose the project */ }
            return f;
        }

        public void Save(string path)
        {
            var root = Obj();
            Put(root, "format", Str("hoard-unity-credits"));
            Put(root, "version", JsonBuild.Num(1));
            Put(root, "title", Str(Title ?? ""));
            Put(root, "style", Str(Format.ToString()));
            var left = new List<string>(LeftOut);
            left.Sort(StringComparer.Ordinal);
            Put(root, "left_out", Arr(left.ConvertAll(Str)));
            Put(root, "added", Arr(Added.ConvertAll(e =>
            {
                var o = Obj();
                Put(o, "name", Str(e.Name ?? ""));
                Put(o, "creator", Str(e.Creator ?? ""));
                Put(o, "url", e.Url == null ? JsonBuild.Null() : Str(e.Url));
                return o;
            })));
            JsonBuild.WriteFile(path, Json.Canonical(root));
        }

        static JsonValue Obj() { return JsonBuild.Obj(); }
        static JsonValue Arr(List<JsonValue> items) { return JsonBuild.Arr(items); }
        static JsonValue Str(string s) { return JsonBuild.Str(s); }
        static void Put(JsonValue o, string k, JsonValue v) { JsonBuild.Put(o, k, v); }
    }
}
