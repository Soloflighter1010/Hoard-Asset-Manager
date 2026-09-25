// A small JSON reader, and the exact writer Hoard's seals are made over (Python's json.dumps with sorted keys,
// no spaces and UTF-8). Hoard's files are data from outside this program: size and nesting are limited, and
// nothing in them is ever run. Plain C# 7, no Unity references, so it can be tested outside Unity.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace SoloFlighter.Hoard
{
    public enum JsonKind { Null, Bool, Number, String, Array, Object }

    public sealed class JsonValue
    {
        public JsonKind Kind;
        public bool Bool;
        public string Text;                                   // a string's value, or a number exactly as written
        public List<JsonValue> Items;                         // arrays
        public List<KeyValuePair<string, JsonValue>> Members; // objects, in file order (a repeated key keeps its last value)

        public JsonValue Get(string key)
        {
            if (Kind != JsonKind.Object) return null;
            foreach (var m in Members) if (m.Key == key) return m.Value;
            return null;
        }

        public string Str(string key)
        {
            var v = Get(key);
            return v != null && v.Kind == JsonKind.String ? v.Text : null;
        }

        public long? Long(string key)
        {
            var v = Get(key);
            long n;
            return v != null && v.Kind == JsonKind.Number && long.TryParse(v.Text, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out n) ? n : (long?)null;
        }

        public List<string> Strings(string key)
        {
            var v = Get(key);
            var list = new List<string>();
            if (v != null && v.Kind == JsonKind.Array)
                foreach (var item in v.Items) if (item.Kind == JsonKind.String) list.Add(item.Text);
            return list;
        }
    }

    public sealed class JsonException : Exception
    {
        public JsonException(string message) : base(message) { }
    }

    public static class Json
    {
        const int MaxDepth = 64;

        public static JsonValue Parse(string text)
        {
            int i = 0;
            var value = ReadValue(text, ref i, 0);
            SkipSpace(text, ref i);
            if (i != text.Length) throw new JsonException("extra text after the JSON");
            return value;
        }

        static void SkipSpace(string s, ref int i)
        {
            while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++;
        }

        static JsonValue ReadValue(string s, ref int i, int depth)
        {
            if (depth > MaxDepth) throw new JsonException("nested too deeply");
            SkipSpace(s, ref i);
            if (i >= s.Length) throw new JsonException("ended early");
            char c = s[i];
            if (c == '{') return ReadObject(s, ref i, depth);
            if (c == '[') return ReadArray(s, ref i, depth);
            if (c == '"') return new JsonValue { Kind = JsonKind.String, Text = ReadString(s, ref i) };
            if (Match(s, ref i, "true")) return new JsonValue { Kind = JsonKind.Bool, Bool = true };
            if (Match(s, ref i, "false")) return new JsonValue { Kind = JsonKind.Bool, Bool = false };
            if (Match(s, ref i, "null")) return new JsonValue { Kind = JsonKind.Null };
            return ReadNumber(s, ref i);
        }

        static bool Match(string s, ref int i, string word)
        {
            if (string.CompareOrdinal(s, i, word, 0, word.Length) != 0) return false;
            i += word.Length;
            return true;
        }

        static JsonValue ReadObject(string s, ref int i, int depth)
        {
            var v = new JsonValue { Kind = JsonKind.Object, Members = new List<KeyValuePair<string, JsonValue>>() };
            i++;
            SkipSpace(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return v; }
            while (true)
            {
                SkipSpace(s, ref i);
                if (i >= s.Length || s[i] != '"') throw new JsonException("expected a name");
                string key = ReadString(s, ref i);
                SkipSpace(s, ref i);
                if (i >= s.Length || s[i] != ':') throw new JsonException("expected ':'");
                i++;
                var item = ReadValue(s, ref i, depth + 1);
                int at = v.Members.FindIndex(m => m.Key == key);
                if (at >= 0) v.Members[at] = new KeyValuePair<string, JsonValue>(key, item);  // as Python: the last one wins
                else v.Members.Add(new KeyValuePair<string, JsonValue>(key, item));
                SkipSpace(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == '}') { i++; return v; }
                throw new JsonException("expected ',' or '}'");
            }
        }

        static JsonValue ReadArray(string s, ref int i, int depth)
        {
            var v = new JsonValue { Kind = JsonKind.Array, Items = new List<JsonValue>() };
            i++;
            SkipSpace(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return v; }
            while (true)
            {
                v.Items.Add(ReadValue(s, ref i, depth + 1));
                SkipSpace(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') { i++; return v; }
                throw new JsonException("expected ',' or ']'");
            }
        }

        static string ReadString(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++;
            while (i < s.Length)
            {
                char c = s[i++];
                if (c == '"') return sb.ToString();
                if (c < 0x20) throw new JsonException("control character in a string");
                if (c != '\\') { sb.Append(c); continue; }
                if (i >= s.Length) break;
                char e = s[i++];
                switch (e)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 > s.Length) throw new JsonException("bad \\u escape");
                        sb.Append((char)int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                        i += 4;
                        break;
                    default: throw new JsonException("bad escape");
                }
            }
            throw new JsonException("string never ends");
        }

        static JsonValue ReadNumber(string s, ref int i)
        {
            int start = i;
            if (i < s.Length && s[i] == '-') i++;
            int digits = i;
            while (i < s.Length && char.IsDigit(s[i]) && s[i] < 128) i++;
            if (i == digits) throw new JsonException("unexpected character");
            if (i < s.Length && s[i] == '.') { i++; while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++; }
            if (i < s.Length && (s[i] == 'e' || s[i] == 'E'))
            {
                i++;
                if (i < s.Length && (s[i] == '+' || s[i] == '-')) i++;
                while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++;
            }
            return new JsonValue { Kind = JsonKind.Number, Text = s.Substring(start, i - start) };
        }

        // ---- the canonical form seals are made over: Python's json.dumps(obj, sort_keys=True,
        // separators=(",", ":"), ensure_ascii=False), encoded as UTF-8.

        public static byte[] Canonical(JsonValue v)
        {
            var sb = new StringBuilder();
            Write(sb, v);
            return new UTF8Encoding(false).GetBytes(sb.ToString());
        }

        static void Write(StringBuilder sb, JsonValue v)
        {
            switch (v.Kind)
            {
                case JsonKind.Null: sb.Append("null"); break;
                case JsonKind.Bool: sb.Append(v.Bool ? "true" : "false"); break;
                case JsonKind.Number: sb.Append(v.Text); break;   // Hoard writes numbers as Python would
                case JsonKind.String: WriteString(sb, v.Text); break;
                case JsonKind.Array:
                    sb.Append('[');
                    for (int n = 0; n < v.Items.Count; n++) { if (n > 0) sb.Append(','); Write(sb, v.Items[n]); }
                    sb.Append(']');
                    break;
                case JsonKind.Object:
                    var members = new List<KeyValuePair<string, JsonValue>>(v.Members);
                    members.Sort((a, b) => CodePointOrder(a.Key, b.Key));
                    sb.Append('{');
                    for (int n = 0; n < members.Count; n++)
                    {
                        if (n > 0) sb.Append(',');
                        WriteString(sb, members[n].Key);
                        sb.Append(':');
                        Write(sb, members[n].Value);
                    }
                    sb.Append('}');
                    break;
            }
        }

        static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        /// <summary>Order by Unicode code point, as Python sorts strings (C#'s ordinal order compares UTF-16 units,
        /// which differs for characters past U+FFFF).</summary>
        public static int CodePointOrder(string a, string b)
        {
            int i = 0, j = 0;
            while (i < a.Length && j < b.Length)
            {
                int ca = char.IsSurrogatePair(a, i) ? char.ConvertToUtf32(a, i) : a[i];
                int cb = char.IsSurrogatePair(b, j) ? char.ConvertToUtf32(b, j) : b[j];
                if (ca != cb) return ca < cb ? -1 : 1;
                i += ca > 0xFFFF ? 2 : 1;
                j += cb > 0xFFFF ? 2 : 1;
            }
            return (a.Length - i).CompareTo(b.Length - j);
        }
    }
}
