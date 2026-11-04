// How the Hoard windows look: the app's own colours (dark, or light with Unity's light skin), its logo, and the
// pieces the app is made of (rounded buttons, pills, store tabs, tiles with a store's colour along their foot),
// drawn with Unity's immediate-mode GUI. Nothing here reads or changes anything: it only draws.
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    /// <summary>How Hoard's window looks: the app's colours, fonts, boxes and buttons, in Unity's light or dark
    /// skin.</summary>
    public static class Look
    {
        // ---- colours: hoard/web/library.html's
        public static bool Dark { get { return EditorGUIUtility.isProSkin; } }
        public static Color Cave { get { return Dark ? Hex(0x211C18) : Hex(0xEEECE8); } }
        public static Color Ledge { get { return Dark ? Hex(0x2B2520) : Hex(0xFFFFFF); } }
        public static Color Stone { get { return Dark ? Hex(0x372F28) : Hex(0xE3DFD8); } }
        public static Color Seam { get { return Dark ? Hex(0x4A4037) : Hex(0xD2CCC3); } }
        public static Color Bone { get { return Dark ? Hex(0xF4EDE3) : Hex(0x211C18); } }
        public static Color Dust { get { return Dark ? Hex(0xB3A695) : Hex(0x6B6157); } }
        public static Color Gold { get { return Dark ? Hex(0xF0B429) : Hex(0xB07A00); } }
        public static Color GoldInk { get { return Dark ? Hex(0x2A1D00) : Hex(0xFFFFFF); } }
        public static Color GoldText { get { return Dark ? Hex(0xF0B429) : Hex(0x7A5100); } }
        public static Color Warn { get { return Dark ? Hex(0xFF9F6B) : Hex(0xB4531B); } }
        public static readonly Color BadgeBack = new Color(20 / 255f, 16 / 255f, 12 / 255f, 0.78f);
        public static readonly Color BadgeText = Hex(0xF4EDE3);

        static readonly Dictionary<string, int[]> StoreColours = new Dictionary<string, int[]>
        {   // dark, light
            { "Booth", new[] { 0xFF6259, 0xD8332B } }, { "Gumroad", new[] { 0xFF8AD8, 0xC8339A } },
            { "Jinxxy", new[] { 0x56D1DC, 0x07808B } }, { "Payhip", new[] { 0x95A0FF, 0x5360D6 } },
            { "Itch", new[] { 0x7ED67A, 0x2B7F35 } }, { "Local", new[] { 0xE8C26A, 0x8A6410 } },
        };

        /// <summary>A store's colour, as the app shows it (its tab, the line along its tiles' foot); gold for none.</summary>
        public static Color Store(string store)
        {
            int[] c;
            return store != null && StoreColours.TryGetValue(store, out c) ? Hex(c[Dark ? 0 : 1]) : Gold;
        }

        /// <summary>A colour from 0xRRGGBB.</summary>
        public static Color Hex(int rgb)
        {
            return new Color(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f, 1);
        }

        /// <summary>A colour, see-through by a.</summary>
        public static Color Alpha(Color c, float a) { c.a = a; return c; }

        /// <summary>A picture's stand-in, as the app's: a soft colour of its own for each product.</summary>
        public static Color Placeholder(string seed)
        {
            int h = 0;
            foreach (char ch in seed ?? "") h = unchecked(h * 31 + ch);
            float hue = ((h % 360) + 360) % 360 / 360f;
            return Hsl(hue, 0.28f, Dark ? 0.30f : 0.82f);
        }

        /// <summary>A colour from hue, saturation and lightness.</summary>
        static Color Hsl(float h, float s, float l)
        {
            float q = l < 0.5f ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
            Func<float, float> f = t =>
            {
                t = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
                return t < 1 / 6f ? p + (q - p) * 6 * t : t < 0.5f ? q : t < 2 / 3f ? p + (q - p) * (2 / 3f - t) * 6 : p;
            };
            return new Color(f(h + 1 / 3f), f(h), f(h - 1 / 3f), 1);
        }

        // ---- drawing

        /// <summary>A filled rectangle, its corners rounded.</summary>
        public static void Fill(Rect r, Color c, float radius = 0)
        {
            if (Event.current.type != EventType.Repaint) return;
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, c, Vector4.zero, Vector4.one * radius);
        }

        /// <summary>A line around a rectangle, inside its edge.</summary>
        public static void Outline(Rect r, Color c, float width, float radius = 0)
        {
            if (Event.current.type != EventType.Repaint) return;
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, c, Vector4.one * width, Vector4.one * radius);
        }

        /// <summary>A picture filling a rectangle (cropped to it), its corners rounded.</summary>
        public static void Picture(Rect r, Texture t, float radius)
        {
            if (Event.current.type != EventType.Repaint || t == null) return;
            GUI.DrawTexture(r, t, ScaleMode.ScaleAndCrop, true, 0, Color.white, Vector4.zero, Vector4.one * radius);
        }

        /// <summary>A product's picture as the app's tiles show it: rounded, with its store's colour along the foot,
        /// or a stand-in with its initials while there's no picture.</summary>
        public static void Art(Rect r, Texture t, string store, string name, float radius = 12)
        {
            const float notch = 5;
            Fill(r, Store(store), radius);
            GUI.BeginClip(new Rect(r.x, r.y, r.width, r.height - notch));
            var inner = new Rect(0, 0, r.width, r.height);
            if (t != null) Picture(inner, t, radius);
            else
            {
                Fill(inner, Placeholder(name), radius);
                if (r.width >= 56)
                {
                    var s = Style("initials", Styles.Initials);
                    s.fontSize = Mathf.RoundToInt(Mathf.Clamp(r.width * 0.22f, 14, 44));
                    GUI.Label(new Rect(0, 0, r.width, r.height - notch), Initials(name), s);
                }
            }
            GUI.EndClip();
        }

        /// <summary>Up to two initials of a name, for a product with no picture.</summary>
        static string Initials(string name)
        {
            var letters = new List<char>();
            foreach (string word in (name ?? "").Split(new[] { ' ', '-', '_', '.', '(', ')', '[', ']', '【', '】' }, StringSplitOptions.RemoveEmptyEntries))
                if (letters.Count < 2 && char.IsLetterOrDigit(word[0])) letters.Add(char.ToUpperInvariant(word[0]));
            return new string(letters.ToArray());
        }

        /// <summary>A small badge on a tile's picture ("In project", "Update"), as wide as its words. Returns its width.</summary>
        public static float Badge(Vector2 at, string text, bool gold, bool rightAligned = false)
        {
            var s = Style("badge", Styles.Badge);
            float w = s.CalcSize(new GUIContent(text)).x + 14;
            var r = new Rect(rightAligned ? at.x - w : at.x, at.y, w, 18);
            Fill(r, gold ? Gold : BadgeBack, 6);
            s.normal.textColor = gold ? GoldInk : BadgeText;
            GUI.Label(r, text, s);
            return w;
        }

        /// <summary>How wide a badge with these words is.</summary>
        public static float BadgeWidth(string text) { return Style("badge", Styles.Badge).CalcSize(new GUIContent(text)).x + 14; }

        static readonly Dictionary<string, GUIStyle> boxes = new Dictionary<string, GUIStyle>();
        static readonly List<Texture2D> boxTextures = new List<Texture2D>();
        static bool boxesDark;

        /// <summary>A box for GUILayout (or GUIStyle.Draw) in the app's look: a rounded fill with a line round it, its
        /// contents padded. key: one per colouring.</summary>
        public static GUIStyle Box(string key, Color fill, Color line, int radius = 10, int padX = 12, int padY = 10)
        {
            if (boxesDark != Dark) { ReleaseBoxes(); boxesDark = Dark; }
            GUIStyle s;
            if (boxes.TryGetValue(key, out s) && s.normal.background != null) return s;
            int n = radius * 2 + 4;
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false) { hideFlags = HideFlags.HideAndDontSave, wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
            var px = new Color[n * n];
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    // distance from the rounded rectangle's edge (negative inside), for smooth corners
                    float cx = Mathf.Clamp(x + 0.5f, radius, n - radius), cy = Mathf.Clamp(y + 0.5f, radius, n - radius);
                    float d = Mathf.Sqrt((x + 0.5f - cx) * (x + 0.5f - cx) + (y + 0.5f - cy) * (y + 0.5f - cy)) - radius;
                    float inside = Mathf.Clamp01(0.5f - d), ring = Mathf.Clamp01(0.5f - d) - Mathf.Clamp01(0.5f - (d + 1));
                    Color c = line.a > 0 ? Color.Lerp(fill, line, ring / Mathf.Max(inside, 0.0001f)) : fill;
                    c.a *= inside;
                    px[y * n + x] = c;
                }
            t.SetPixels(px);
            t.Apply();
            boxTextures.Add(t);
            s = new GUIStyle { border = new RectOffset(radius + 1, radius + 1, radius + 1, radius + 1),
                               padding = new RectOffset(padX, padX, padY, padY), margin = new RectOffset(0, 0, 3, 3) };
            s.normal.background = t;
            boxes[key] = s;
            return s;
        }

        /// <summary>Free the boxes' textures (when the skin changes, or the window closes).</summary>
        static void ReleaseBoxes()
        {
            foreach (var t in boxTextures) if (t != null) UnityEngine.Object.DestroyImmediate(t);
            boxTextures.Clear();
            boxes.Clear();
        }

        /// <summary>A diamond in a store's colour, as the app marks its stores.</summary>
        public static void Dot(Vector2 centre, Color c, float size = 7)
        {
            if (Event.current.type != EventType.Repaint) return;
            var m = GUI.matrix;
            GUIUtility.RotateAroundPivot(45, centre);
            Fill(new Rect(centre.x - size / 2, centre.y - size / 2, size, size), c, 2);
            GUI.matrix = m;
        }

        /// <summary>A kind of button.</summary>
        public enum Kind { Ghost, Primary, Pill, PillOn }

        /// <summary>A button as the app draws them: Ghost (ledge, with a seam), Primary (gold), or a filter Pill (gold
        /// when it's on).</summary>
        public static bool Button(Rect r, GUIContent text, Kind kind)
        {
            bool hover = GUI.enabled && r.Contains(Event.current.mousePosition);
            if (Event.current.type == EventType.Repaint)
            {
                float radius = kind == Kind.Pill || kind == Kind.PillOn ? r.height / 2 : 8;
                Color back = kind == Kind.Primary || kind == Kind.PillOn ? Gold : hover ? Stone : Ledge;
                if (hover && (kind == Kind.Primary || kind == Kind.PillOn)) back = Color.Lerp(back, Color.white, 0.08f);
                if (!GUI.enabled) back = Alpha(back, 0.5f);
                Fill(r, back, radius);
                if (kind == Kind.Ghost || kind == Kind.Pill) Outline(r, Alpha(Seam, GUI.enabled ? 1 : 0.5f), 1, radius);
                var s = Style("button", Styles.ButtonText);
                Color ink = kind == Kind.Primary || kind == Kind.PillOn ? GoldInk : Bone;
                s.normal.textColor = GUI.enabled ? ink : Alpha(ink, 0.5f);
                GUI.Label(r, new GUIContent(text.text), s);
            }
            return GUI.Button(r, new GUIContent("", text.tooltip), GUIStyle.none);
        }

        /// <summary>A button with words.</summary>
        public static bool Button(Rect r, string text, Kind kind = Kind.Ghost) { return Button(r, new GUIContent(text), kind); }

        /// <summary>The width a button needs for its words.</summary>
        public static float ButtonWidth(string text) { return Style("button", Styles.ButtonText).CalcSize(new GUIContent(text)).x + 24; }

        public const float ButtonHeight = 26;

        /// <summary>A button in a GUILayout row.</summary>
        public static bool LayoutButton(string text, Kind kind = Kind.Ghost, string tooltip = null)
        {
            var r = GUILayoutUtility.GetRect(ButtonWidth(text), ButtonHeight, GUILayout.Width(ButtonWidth(text)), GUILayout.Height(ButtonHeight));
            return Button(r, new GUIContent(text, tooltip), kind);
        }

        // ---- text styles, made once for each skin

        /// <summary>The text styles the window uses.</summary>
        public enum Styles { Body, Dust, Small, Name, Title, Heading, HeadingDust, Badge, ButtonText, Initials, Tab, TabCount, Section, Wrapped, Centered }

        static readonly Dictionary<string, GUIStyle> styles = new Dictionary<string, GUIStyle>();
        static bool stylesDark;

        /// <summary>A text style in the app's colours. key: one per use whose colour or size is changed while drawing.</summary>
        public static GUIStyle Style(string key, Styles kind)
        {
            if (stylesDark != Dark) { styles.Clear(); stylesDark = Dark; }
            GUIStyle s;
            if (styles.TryGetValue(key, out s)) return s;
            s = new GUIStyle(EditorStyles.label) { richText = false, clipping = TextClipping.Clip, wordWrap = false };
            Color ink = Bone;
            switch (kind)
            {
                case Styles.Dust: ink = Dust; break;
                case Styles.Small: ink = Dust; s.fontSize = 11; break;
                case Styles.Name: s.fontStyle = FontStyle.Bold; s.fontSize = 12; s.wordWrap = true; s.alignment = TextAnchor.UpperLeft; break;
                case Styles.Title: s.fontStyle = FontStyle.Bold; s.fontSize = 16; s.wordWrap = true; break;
                case Styles.Heading: s.fontStyle = FontStyle.Bold; s.fontSize = 18; break;
                case Styles.HeadingDust: ink = Dust; s.fontStyle = FontStyle.Bold; s.fontSize = 18; break;
                case Styles.Badge: s.fontStyle = FontStyle.Bold; s.fontSize = 10; s.alignment = TextAnchor.MiddleCenter; s.padding = new RectOffset(0, 0, 0, 1); break;
                case Styles.ButtonText: s.fontStyle = FontStyle.Bold; s.fontSize = 12; s.alignment = TextAnchor.MiddleCenter; s.padding = new RectOffset(0, 0, 0, 1); break;
                case Styles.Initials: ink = Alpha(Bone, 0.85f); s.fontStyle = FontStyle.Bold; s.alignment = TextAnchor.MiddleCenter; break;
                case Styles.Tab: ink = Dust; s.fontStyle = FontStyle.Bold; s.fontSize = 12; s.alignment = TextAnchor.MiddleLeft; break;
                case Styles.TabCount: ink = Dust; s.fontSize = 11; s.alignment = TextAnchor.MiddleLeft; break;
                case Styles.Section: ink = Dust; s.fontStyle = FontStyle.Bold; s.fontSize = 11; break;
                case Styles.Wrapped: s.wordWrap = true; break;
                case Styles.Centered: ink = Dust; s.wordWrap = true; s.alignment = TextAnchor.UpperCenter; break;
            }
            s.normal.textColor = s.hover.textColor = s.active.textColor = s.focused.textColor = ink;
            styles[key] = s;
            return s;
        }

        /// <summary>A text style, made once for each skin.</summary>
        public static GUIStyle Style(Styles kind) { return Style(kind.ToString(), kind); }

        static GUIStyle searchField;

        /// <summary>A text field with nothing of its own to draw (a plain style, not the editor's field): the search
        /// box's rounded ledge is drawn under it.</summary>
        public static GUIStyle SearchField
        {
            get
            {
                if (searchField != null && stylesDark == Dark) return searchField;
                var s = new GUIStyle { font = EditorStyles.label.font, fontSize = 12, alignment = TextAnchor.MiddleLeft, clipping = TextClipping.Clip,
                                       wordWrap = false, padding = new RectOffset(0, 0, 0, 0) };
                foreach (var state in new[] { s.normal, s.hover, s.focused, s.active, s.onNormal, s.onHover, s.onFocused, s.onActive })
                    state.textColor = Bone;
                return searchField = s;
            }
        }

        // ---- the logo

        static Texture2D logoDark, logoLight;

        /// <summary>Hoard's logo (the boxes and the word, 226 × 64 as the app draws it), for this skin.</summary>
        public static Texture2D Logo
        {
            get
            {
                if (Dark) return logoDark != null ? logoDark : (logoDark = FromPng(LogoDarkPng));
                return logoLight != null ? logoLight : (logoLight = FromPng(LogoLightPng));
            }
        }

        /// <summary>Draw the logo this tall at a point; just the boxes when compact. Returns the width it took.</summary>
        public static float DrawLogo(Vector2 at, float height, bool compact)
        {
            var t = Logo;
            float full = height * 226 / 64f, w = compact ? height : full;
            if (t != null && Event.current.type == EventType.Repaint)
                GUI.DrawTextureWithTexCoords(new Rect(at.x, at.y, w, height), t, new Rect(0, 0, w / full, 1), true);
            return w;
        }

        /// <summary>A texture from a PNG, as base64.</summary>
        static Texture2D FromPng(string base64)
        {
            var t = new Texture2D(2, 2, TextureFormat.RGBA32, false) { hideFlags = HideFlags.HideAndDontSave, filterMode = FilterMode.Bilinear };
            try { t.LoadImage(Convert.FromBase64String(base64)); }
            catch (Exception) { UnityEngine.Object.DestroyImmediate(t); return null; }
            return t;
        }

        /// <summary>Let go of the textures made here (a window closing).</summary>
        public static void Release()
        {
            foreach (var t in new[] { logoDark, logoLight })
                if (t != null) UnityEngine.Object.DestroyImmediate(t);
            logoDark = logoLight = null;
            ReleaseBoxes();
        }

        // The logo, drawn from scripts/site_chrome.py's LOGO at twice its size (452 × 128) with the word in Bone (dark)
        // or Cave's ink (light), in 64 colours: the package ships code only.
        const string LogoDarkPng = "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";
        const string LogoLightPng = "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";
    }
}
