// GIF pictures, animated ones included, for the Hoard window: Unity's Texture2D.LoadImage reads only PNG and JPEG,
// and Hoard saves a store's animated picture as _thumbnail.gif. Every frame is put together as a browser shows it
// (transparency, interlacing, each frame's disposal), and made no bigger than a thumbnail needs, so a long animation
// can't fill the editor's memory. The file could be anything, so every size and code is checked, and a damaged file
// gives what could be read, or null. Plain C#, no Unity references.
using System;
using System.Collections.Generic;

namespace SoloFlighter.Hoard
{
    public sealed class GifImage
    {
        public int Width, Height;                                   // after shrinking to fit
        public List<byte[]> Frames = new List<byte[]>();            // RGBA, 4 bytes a pixel, rows from the bottom (as Unity's textures are)
        public List<int> DelaysMs = new List<int>();                // how long each frame shows
        public int TotalMs { get { int t = 0; foreach (int d in DelaysMs) t += d; return t; } }

        /// <summary>Which frame shows at this moment of a looping animation.</summary>
        public int FrameAt(double ms)
        {
            if (Frames.Count <= 1) return 0;
            int total = TotalMs;
            if (total <= 0) return 0;
            double t = ms % total;
            if (t < 0) t += total;
            for (int i = 0; i < DelaysMs.Count; i++)
            {
                if (t < DelaysMs[i]) return i;
                t -= DelaysMs[i];
            }
            return Frames.Count - 1;
        }
    }

    public static class GifDecoder
    {
        public const int MaxCanvas = 4096;                  // a side of the picture, as the file gives it
        public const int MaxFrames = 200;
        public const long MaxFrameBytes = 16L * 1024 * 1024; // all the frames kept, after shrinking

        public static bool IsGif(byte[] data)
        {
            return data != null && data.Length >= 6 && data[0] == 'G' && data[1] == 'I' && data[2] == 'F' && data[3] == '8' &&
                   (data[4] == '7' || data[4] == '9') && data[5] == 'a';
        }

        /// <summary>Decode a GIF, each frame shrunk to fit within maxSide pixels. Null when it isn't a GIF, or not
        /// even one frame could be read.</summary>
        public static GifImage Decode(byte[] data, int maxSide = 256)
        {
            try { return DecodeOrThrow(data, Math.Max(1, maxSide)); }
            catch (Exception) { return null; }
        }

        sealed class Reader
        {
            readonly byte[] d;
            public int Pos;
            public Reader(byte[] data) { d = data; }
            public bool More { get { return Pos < d.Length; } }
            public int Byte() { if (Pos >= d.Length) throw new FormatException("the file ends early"); return d[Pos++]; }
            public int Short() { int lo = Byte(); return lo | (Byte() << 8); }
            public byte[] Bytes(int n)
            {
                if (n < 0 || Pos + n > d.Length) throw new FormatException("the file ends early");
                var b = new byte[n];
                Buffer.BlockCopy(d, Pos, b, 0, n);
                Pos += n;
                return b;
            }
            /// <summary>Data sub-blocks, joined (a count byte, that many bytes, ... a zero). A file that ends early
            /// gives what there was.</summary>
            public byte[] Blocks()
            {
                var all = new List<byte>();
                while (Pos < d.Length)
                {
                    int n = d[Pos++];
                    if (n == 0) break;
                    int take = Math.Min(n, d.Length - Pos);
                    for (int i = 0; i < take; i++) all.Add(d[Pos + i]);
                    Pos += take;
                }
                return all.ToArray();
            }
            public void SkipBlocks()
            {
                while (Pos < d.Length)
                {
                    int n = d[Pos++];
                    if (n == 0) break;
                    Pos += n;
                }
            }
        }

        static GifImage DecodeOrThrow(byte[] data, int maxSide)
        {
            if (!IsGif(data)) return null;
            var r = new Reader(data) { Pos = 6 };
            int w = r.Short(), h = r.Short(), packed = r.Byte();
            r.Byte(); r.Byte();   // background colour (browsers show transparency instead), aspect ratio
            if (w <= 0 || h <= 0 || w > MaxCanvas || h > MaxCanvas) return null;
            byte[] global = (packed & 0x80) != 0 ? r.Bytes(3 * (2 << (packed & 7))) : null;

            // the picture made smaller (never larger) to fit maxSide, keeping its shape
            double scale = Math.Min(1.0, (double)maxSide / Math.Max(w, h));
            int ow = Math.Max(1, (int)Math.Round(w * scale)), oh = Math.Max(1, (int)Math.Round(h * scale));
            var img = new GifImage { Width = ow, Height = oh };
            long frameBytes = (long)ow * oh * 4;
            var canvas = new byte[w * h * 4];   // top row first, while putting frames together
            int delay = 0, transparent = -1, disposal = 0;

            while (r.More)
            {
                try { if (!NextBlock(r, img, ref canvas, w, h, ow, oh, frameBytes, global, ref delay, ref transparent, ref disposal)) break; }
                catch (FormatException) { break; }   // the file ends early: keep the frames already read
            }
            return img.Frames.Count > 0 ? img : null;
        }

        /// <summary>Read one block: an extension, a frame (drawn, and kept when there's room), or the end. False when
        /// there's nothing more to read.</summary>
        static bool NextBlock(Reader r, GifImage img, ref byte[] canvas, int w, int h, int ow, int oh, long frameBytes,
                              byte[] global, ref int delay, ref int transparent, ref int disposal)
        {
            int block = r.Byte();
            if (block == 0x3B) return false;                           // the end
            if (block == 0x21)                                         // an extension
            {
                int label = r.Byte();
                if (label == 0xF9)                                     // how the next frame shows
                {
                    byte[] g = r.Blocks();
                    if (g.Length >= 4)
                    {
                        disposal = (g[0] >> 2) & 7;
                        delay = (g[1] | (g[2] << 8)) * 10;
                        transparent = (g[0] & 1) != 0 ? g[3] : -1;
                    }
                }
                else r.SkipBlocks();
                return true;
            }
            if (block != 0x2C) return false;                           // not GIF any more: keep what we have

            int fx = r.Short(), fy = r.Short(), fw = r.Short(), fh = r.Short(), fp = r.Byte();
            byte[] colours = (fp & 0x80) != 0 ? r.Bytes(3 * (2 << (fp & 7))) : global;
            bool interlaced = (fp & 0x40) != 0;
            int minCode = r.Byte();
            byte[] lzw = r.Blocks();
            if (colours == null || fw <= 0 || fh <= 0 || fw > MaxCanvas || fh > MaxCanvas || minCode < 2 || minCode > 11)
            {
                delay = 0; transparent = -1; disposal = 0;
                return true;                                           // a frame that can't be drawn is left out
            }
            byte[] before = disposal == 3 ? (byte[])canvas.Clone() : null;
            byte[] indexes = Lzw(lzw, minCode, fw * fh);
            Draw(canvas, w, h, indexes, fx, fy, fw, fh, interlaced, colours, transparent);

            if (img.Frames.Count < MaxFrames && (img.Frames.Count + 1) * frameBytes <= MaxFrameBytes)
            {
                img.Frames.Add(Shrink(canvas, w, h, ow, oh));
                img.DelaysMs.Add(delay < 20 ? 100 : delay);            // as browsers do: 0 or 10 ms shows as 100
            }
            else if (img.Frames.Count > 0) return false;               // enough: the animation is cut short

            if (disposal == 2) Clear(canvas, w, h, fx, fy, fw, fh);    // back to transparent, for the next frame
            else if (disposal == 3 && before != null) canvas = before; // back to how it was before this frame
            delay = 0; transparent = -1; disposal = 0;
            return true;
        }

        /// <summary>GIF's LZW: the colour indexes of one frame (count of them; missing ones are 0).</summary>
        static byte[] Lzw(byte[] data, int minCode, int count)
        {
            var output = new byte[count];
            int clear = 1 << minCode, end = clear + 1;
            var prefix = new short[4096];
            var suffix = new byte[4096];
            var first = new byte[4096];
            var stack = new byte[4097];
            for (int i = 0; i < clear; i++) { prefix[i] = -1; suffix[i] = (byte)i; first[i] = (byte)i; }
            int size = minCode + 1, next = end + 1, old = -1, outPos = 0;
            int bits = 0, value = 0, pos = 0;
            while (outPos < count)
            {
                while (bits < size)
                {
                    if (pos >= data.Length) return output;                 // the data ends early: the rest stays 0
                    value |= data[pos++] << bits;
                    bits += 8;
                }
                int code = value & ((1 << size) - 1);
                value >>= size;
                bits -= size;
                if (code == clear) { size = minCode + 1; next = end + 1; old = -1; continue; }
                if (code == end) break;
                int sp = 0, c;
                if (old == -1)
                {
                    if (code >= clear) break;                              // a first code must be a colour
                    output[outPos++] = (byte)code;
                    old = code;
                    continue;
                }
                if (code < next) c = code;
                else if (code == next) { stack[sp++] = first[old]; c = old; }
                else break;                                                // a code that can't exist yet: damaged
                while (c >= clear)
                {
                    if (sp >= stack.Length - 1) return output;
                    stack[sp++] = suffix[c];
                    c = prefix[c];
                    if (c < 0) break;
                }
                if (c >= 0) stack[sp++] = (byte)c;
                byte head = stack[sp - 1];
                while (sp > 0 && outPos < count) output[outPos++] = stack[--sp];
                if (next < 4096)
                {
                    prefix[next] = (short)old;
                    suffix[next] = head;
                    first[next] = first[old];
                    next++;
                    if (next == (1 << size) && size < 12) size++;
                }
                old = code;
            }
            return output;
        }

        static void Draw(byte[] canvas, int w, int h, byte[] indexes, int fx, int fy, int fw, int fh, bool interlaced,
                         byte[] colours, int transparent)
        {
            int ncolours = colours.Length / 3;
            int row = 0, pass = 0, step = interlaced ? 8 : 1;
            for (int line = 0; line < fh; line++)
            {
                int y = fy + row;
                if (y >= 0 && y < h)
                    for (int x = 0; x < fw; x++)
                    {
                        int cx = fx + x;
                        if (cx >= w) break;
                        int idx = indexes[line * fw + x];
                        if (idx == transparent || idx >= ncolours) continue;
                        int o = (y * w + cx) * 4;
                        canvas[o] = colours[idx * 3];
                        canvas[o + 1] = colours[idx * 3 + 1];
                        canvas[o + 2] = colours[idx * 3 + 2];
                        canvas[o + 3] = 255;
                    }
                row += step;
                while (interlaced && row >= fh && pass < 3)   // the next pass: rows 4, 12, ...; then 2, 6, ...; then 1, 3, ...
                {
                    pass++;
                    row = pass == 1 ? 4 : pass == 2 ? 2 : 1;
                    step = pass == 1 ? 8 : pass == 2 ? 4 : 2;
                }
            }
        }

        static void Clear(byte[] canvas, int w, int h, int fx, int fy, int fw, int fh)
        {
            for (int y = Math.Max(0, fy); y < Math.Min(h, fy + fh); y++)
                for (int x = Math.Max(0, fx); x < Math.Min(w, fx + fw); x++)
                    Array.Clear(canvas, (y * w + x) * 4, 4);
        }

        /// <summary>The canvas at the new size (each pixel the average of the ones it covers), rows from the bottom.</summary>
        static byte[] Shrink(byte[] canvas, int w, int h, int ow, int oh)
        {
            var o = new byte[ow * oh * 4];
            for (int y = 0; y < oh; y++)
            {
                int y0 = y * h / oh, y1 = Math.Max(y0 + 1, (y + 1) * h / oh);
                int dest = (oh - 1 - y) * ow * 4;
                for (int x = 0; x < ow; x++)
                {
                    int x0 = x * w / ow, x1 = Math.Max(x0 + 1, (x + 1) * w / ow);
                    long r = 0, g = 0, b = 0, a = 0;
                    for (int sy = y0; sy < y1; sy++)
                        for (int sx = x0; sx < x1; sx++)
                        {
                            int s = (sy * w + sx) * 4, alpha = canvas[s + 3];
                            r += canvas[s] * alpha; g += canvas[s + 1] * alpha; b += canvas[s + 2] * alpha; a += alpha;
                        }
                    int n = (y1 - y0) * (x1 - x0), d = dest + x * 4;
                    if (a > 0) { o[d] = (byte)(r / a); o[d + 1] = (byte)(g / a); o[d + 2] = (byte)(b / a); }
                    o[d + 3] = (byte)(a / n);
                }
            }
            return o;
        }
    }
}
