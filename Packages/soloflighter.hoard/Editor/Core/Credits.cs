// A credits list for a project: the creators of the assets it uses, to paste where you share your avatar or world
// (issue #51). Plain C#, no Unity references: the window works out which assets are used, and this makes the list.
using System;
using System.Collections.Generic;
using System.Text;

namespace SoloFlighter.Hoard
{
    public sealed class CreditEntry
    {
        public string Store, Name, Creator, Url;
        public bool Added;              // written in by hand, not found through Hoard
        public string Key { get { return (Store ?? "") + "/" + (Name ?? ""); } }
    }

    public enum CreditFormat { List, Markdown, ByCreator }

    public static class Credits
    {
        public static readonly string[] FormatNames = { "List", "Markdown", "By creator" };

        /// <summary>One entry per product (the first seen wins, so pass the catalog's before the import log's), none
        /// left out by hand, every text made safe to paste and every link checked, sorted by creator then name.</summary>
        public static List<CreditEntry> Build(IEnumerable<CreditEntry> found, ICollection<string> leftOut)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var list = new List<CreditEntry>();
            foreach (var e in found)
            {
                if (e == null) continue;
                var c = new CreditEntry { Store = OneLine(e.Store, 40), Name = OneLine(e.Name, 300), Creator = OneLine(e.Creator, 200),
                                          Added = e.Added };
                if (c.Name.Length == 0) continue;
                c.Url = Link(e.Store, e.Url, e.Added);
                if (!seen.Add(c.Key) || (leftOut != null && leftOut.Contains(c.Key))) continue;
                list.Add(c);
            }
            list.Sort(Order);
            return list;
        }

        static int Order(CreditEntry x, CreditEntry y)
        {
            int c = string.Compare(Who(x), Who(y), StringComparison.CurrentCultureIgnoreCase);
            return c != 0 ? c : string.Compare(x.Name, y.Name, StringComparison.CurrentCultureIgnoreCase);
        }

        static string Who(CreditEntry e) { return e.Creator.Length > 0 ? e.Creator : "Unknown creator"; }

        /// <summary>The list, ready to paste.</summary>
        public static string Format(List<CreditEntry> entries, CreditFormat format, string title = "Assets used")
        {
            var sb = new StringBuilder();
            if (!string.IsNullOrEmpty(title)) sb.Append(format == CreditFormat.Markdown ? "## " + Md(title) : title).Append('\n');
            if (entries.Count == 0) return sb.Append(format == CreditFormat.Markdown ? "\n_None yet._\n" : "None yet.\n").ToString();
            if (format == CreditFormat.Markdown) sb.Append('\n');
            if (format == CreditFormat.ByCreator)
            {
                for (int i = 0; i < entries.Count;)
                {
                    string who = Who(entries[i]);
                    var names = new List<string>();
                    for (; i < entries.Count && Who(entries[i]) == who; i++) names.Add(entries[i].Name);
                    sb.Append(who).Append(": ").Append(string.Join(", ", names)).Append('\n');
                }
                return sb.ToString();
            }
            foreach (var e in entries)
            {
                string store = e.Store.Length > 0 ? HoardCatalog.StoreLabel(e.Store) : "";
                if (format == CreditFormat.Markdown)
                {
                    sb.Append("- ").Append(e.Url != null ? "[" + Md(e.Name) + "](" + e.Url + ")" : Md(e.Name))
                      .Append(" by ").Append(Md(Who(e)));
                    if (store.Length > 0) sb.Append(" (").Append(Md(store)).Append(')');
                }
                else
                {
                    sb.Append("- ").Append(e.Name).Append(" by ").Append(Who(e));
                    if (store.Length > 0) sb.Append(" (").Append(store).Append(')');
                    if (e.Url != null) sb.Append(' ').Append(e.Url);
                }
                sb.Append('\n');
            }
            return sb.ToString();
        }

        /// <summary>One line of plain text: control and invisible formatting characters (a right-to-left override,
        /// say) become spaces, runs of spaces one, and it's cut to max characters.</summary>
        public static string OneLine(string s, int max)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (char ch in s)
            {
                bool odd = char.IsControl(ch) || char.GetUnicodeCategory(ch) == System.Globalization.UnicodeCategory.Format;
                char c = odd || char.IsWhiteSpace(ch) ? ' ' : ch;
                if (c == ' ' && (sb.Length == 0 || sb[sb.Length - 1] == ' ')) continue;
                sb.Append(c);
            }
            string t = sb.ToString().TrimEnd();
            if (t.Length > max) t = t.Substring(0, max).TrimEnd();
            if (t.Length > 0 && char.IsHighSurrogate(t[t.Length - 1])) t = t.Substring(0, t.Length - 1);   // not half a character
            return t;
        }

        /// <summary>A link worth printing: the product's own store page (as the catalog checks it), or, for an entry
        /// written in by hand, any plain https address. Null otherwise.</summary>
        public static string Link(string store, string url, bool added)
        {
            if (string.IsNullOrEmpty(url) || url.Length > 500) return null;
            if (!added) return HoardCatalog.StoreLink(store, url) ? url : null;
            Uri u;
            if (!Uri.TryCreate(url, UriKind.Absolute, out u) || u.Scheme != "https" || !string.IsNullOrEmpty(u.UserInfo)) return null;
            foreach (char c in url) if (char.IsWhiteSpace(c) || char.IsControl(c) || c == '(' || c == ')' || c == '<' || c == '>') return null;
            return url;
        }

        /// <summary>Text as itself in Markdown: characters that would make a link, emphasis or heading are escaped.</summary>
        public static string Md(string s)
        {
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                if ("\\`*_{}[]()<>#+-.!|~".IndexOf(c) >= 0) sb.Append('\\');
                sb.Append(c);
            }
            return sb.ToString();
        }
    }
}
