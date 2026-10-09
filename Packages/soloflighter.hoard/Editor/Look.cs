// How the Hoard windows look: the app's own colours (dark, or light with Unity's light skin), its logo, and the
// pieces the app is made of (rounded buttons, pills, store tabs, tiles with a store's colour along their foot),
// drawn with Unity's immediate-mode GUI. Nothing here reads or changes anything: it only draws.
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
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

        public static Color Hex(int rgb)
        {
            return new Color(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f, 1);
        }

        public static Color Alpha(Color c, float a) { c.a = a; return c; }

        /// <summary>A picture's stand-in, as the app's: a soft colour of its own for each product.</summary>
        public static Color Placeholder(string seed)
        {
            int h = 0;
            foreach (char ch in seed ?? "") h = unchecked(h * 31 + ch);
            float hue = ((h % 360) + 360) % 360 / 360f;
            return Hsl(hue, 0.28f, Dark ? 0.30f : 0.82f);
        }

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

        public static GUIStyle Style(Styles kind) { return Style(kind.ToString(), kind); }

        static GUIStyle searchField;

        /// <summary>A text field with nothing of its own to draw: the search box's rounded ledge is drawn under it.</summary>
        public static GUIStyle SearchField
        {
            get
            {
                if (searchField != null && stylesDark == Dark) return searchField;
                var s = new GUIStyle(EditorStyles.textField) { fontSize = 12, padding = new RectOffset(0, 0, 0, 0), margin = new RectOffset(0, 0, 0, 0),
                                                               border = new RectOffset(0, 0, 0, 0), alignment = TextAnchor.MiddleLeft };
                foreach (var state in new[] { s.normal, s.hover, s.focused, s.active, s.onNormal, s.onHover, s.onFocused, s.onActive })
                {
                    state.background = null;
                    state.scaledBackgrounds = new Texture2D[0];
                    state.textColor = Bone;
                }
                return searchField = s;
            }
        }

        // ---- the logo, and the glow behind the tiles

        static Texture2D logoDark, logoLight, glow;

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

        /// <summary>A soft round light, brightest in the middle, for the glow of the stores' colours.</summary>
        public static Texture2D Glow
        {
            get
            {
                if (glow != null) return glow;
                const int n = 64;
                glow = new Texture2D(n, n, TextureFormat.RGBA32, false) { hideFlags = HideFlags.HideAndDontSave, wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
                var px = new Color32[n * n];
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float dx = (x + 0.5f) / n * 2 - 1, dy = (y + 0.5f) / n * 2 - 1;
                        float d = Mathf.Clamp01(1 - Mathf.Sqrt(dx * dx + dy * dy));
                        px[y * n + x] = new Color32(255, 255, 255, (byte)(255 * d * d));
                    }
                glow.SetPixels32(px);
                glow.Apply();
                return glow;
            }
        }

        /// <summary>The glow rising from the bottom of an area, as in the app's library: the shown store's colour, or
        /// every store's for Everything.</summary>
        public static void DrawGlow(Rect area, string store)
        {
            if (Event.current.type != EventType.Repaint) return;
            float strength = Dark ? 0.22f : 0.16f;
            string[] stores = store == null ? new[] { "Booth", "Gumroad", "Jinxxy", "Payhip", "Itch" } : new[] { store, store, store };
            float w = area.width / stores.Length * 2.2f, h = Mathf.Min(area.height * 0.9f, 520);
            for (int i = 0; i < stores.Length; i++)
            {
                float cx = area.x + area.width * (i + 0.5f) / stores.Length;
                GUI.DrawTexture(new Rect(cx - w / 2, area.yMax - h * 0.55f, w, h), Glow, ScaleMode.StretchToFill, true, 0,
                                Alpha(Store(stores[i]), strength), 0, 0);
            }
        }

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
            foreach (var t in new[] { logoDark, logoLight, glow })
                if (t != null) UnityEngine.Object.DestroyImmediate(t);
            logoDark = logoLight = glow = null;
            ReleaseBoxes();
        }

        // The logo, drawn from scripts/site_chrome.py's LOGO at twice its size (452 × 128) with the word in Bone (dark)
        // or Cave's ink (light), in 64 colours: the package ships code only.
        const string LogoDarkPng = "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";
        const string LogoLightPng = "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";
    }
}
