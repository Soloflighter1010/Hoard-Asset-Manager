// Product pictures for the Hoard window, loaded only for rows being drawn: the file is read (and a GIF decoded, every
// frame, at thumbnail size) on a background thread, then made into textures on Unity's main thread a few per frame.
// Only the most recently used are kept, within a memory budget, and never one that's on screen (PictureShelf, issue
// #407). A still picture is kept no bigger than it's drawn. Animated GIFs play wherever they're drawn.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    /// <summary>Products' pictures, read in the background and kept (within a count and a memory budget), GIFs
    /// animated.</summary>
    public sealed class ThumbnailCache
    {
        const int Capacity = 256;                     // pictures kept at once
        const long Budget = 256L * 1024 * 1024;       // and the memory they may use
        const int DecodePerFrame = 6;                 // made into textures per editor update, so scrolling stays smooth
        const long MaxBytes = 8L * 1024 * 1024;       // a picture file bigger than this isn't read
        const int GifSide = 160;                      // a GIF's frames are kept at most this big: the size it's shown at
        const int StillSide = 480;                    // and a still picture: the details' 240, on a screen at twice that
        const int Readers = 2;                        // files read and GIFs decoded at once, however fast the list scrolls

        /// <summary>A picture as textures: one frame, or a GIF's frames and their timing.</summary>
        sealed class Picture
        {
            public Texture2D[] Frames;                 // one for a still picture
            public GifImage Timing;                    // null for a still picture
            public long Bytes;
        }

        /// <summary>A picture as read from disk, before it's made into textures.</summary>
        sealed class Read { public string Path; public int Generation; public byte[] Still; public GifImage Gif; }

        readonly Dictionary<string, Picture> ready = new Dictionary<string, Picture>();   // the pictures made
        readonly PictureShelf shelf = new PictureShelf(Capacity, Budget);                // which to keep, ask for, let go
        readonly ConcurrentQueue<Read> read = new ConcurrentQueue<Read>();
        readonly ConcurrentQueue<Read> toRead = new ConcurrentQueue<Read>();
        int readers;
        volatile int generation;   // Clear starts a new one: a read asked for before it is dropped, not kept
        double animatedDrawnAt = -1;

        /// <summary>Animated pictures shown as a still of their first frame, as the app's Pause animated pictures.</summary>
        public bool Paused;

        /// <summary>The picture (for an animated GIF, the frame showing now), or null while it's loading (or when
        /// there isn't one).</summary>
        public Texture2D Get(string path)
        {
            if (path == null) return null;
            double now = EditorApplication.timeSinceStartup;
            if (shelf.Drawn(path, now))   // (not kept, or a while since it couldn't be read)
            {
                toRead.Enqueue(new Read { Path = path, Generation = generation });
                StartReader();
            }
            Picture p;
            if (!ready.TryGetValue(path, out p)) return null;
            if (p.Timing == null || p.Frames.Length == 1 || Paused) return p.Frames[0];
            animatedDrawnAt = now;
            return p.Frames[Math.Min(p.Frames.Length - 1, p.Timing.FrameAt(now * 1000))];
        }

        void StartReader()
        {
            if (Interlocked.Increment(ref readers) <= Readers) Task.Run(ReadSome);
            else Interlocked.Decrement(ref readers);
        }

        void ReadSome()
        {
            try
            {
                Read r;
                while (toRead.TryDequeue(out r))
                {
                    if (r.Generation != generation) continue;   // asked for before a Clear
                    try
                    {
                        if (new FileInfo(r.Path).Length <= MaxBytes)
                        {
                            byte[] bytes = File.ReadAllBytes(r.Path);
                            if (GifDecoder.IsGif(bytes)) r.Gif = GifDecoder.Decode(bytes, GifSide);   // null if it can't be read
                            else r.Still = bytes;
                        }
                    }
                    catch (Exception) { r.Still = null; r.Gif = null; }
                    read.Enqueue(r);
                }
            }
            finally
            {
                Interlocked.Decrement(ref readers);
                if (!toRead.IsEmpty) StartReader();   // one queued just as this reader was finishing
            }
        }

        /// <summary>True while an animated picture is on screen, so the window keeps redrawing to play it.</summary>
        public bool Animating { get { return animatedDrawnAt >= 0 && EditorApplication.timeSinceStartup - animatedDrawnAt < 0.5; } }

        /// <summary>Make a few pictures that have been read into textures. Call from the editor's update; true if any
        /// are new.</summary>
        public bool Pump()
        {
            bool any = false;
            double now = EditorApplication.timeSinceStartup;
            Read item;
            for (int n = 0; n < DecodePerFrame && read.TryDequeue(out item); n++)
            {
                if (item.Generation != generation) continue;   // read for before a Clear: nothing kept of it
                Picture had;
                if (ready.TryGetValue(item.Path, out had)) { Destroy(had); ready.Remove(item.Path); }   // never two
                var p = Make(item);
                if (p != null) { ready[item.Path] = p; shelf.Kept(item.Path, p.Bytes, now); }
                else shelf.Failed(item.Path, now);   // (asked for again in a while: Hoard may save it later)
                any = true;
            }
            foreach (string old in shelf.ToForget(now))   // the least recently drawn, never one on screen now
            {
                Picture p;
                if (ready.TryGetValue(old, out p)) { Destroy(p); ready.Remove(old); }
            }
            return any;
        }

        /// <summary>Make a picture's textures (on the main thread, as Unity needs).</summary>
        static Picture Make(Read item)
        {
            if (item.Gif != null)
            {
                var g = item.Gif;
                var frames = new Texture2D[g.Frames.Count];
                try
                {
                    for (int i = 0; i < frames.Length; i++)
                    {
                        frames[i] = new Texture2D(g.Width, g.Height, TextureFormat.RGBA32, false)
                            { hideFlags = HideFlags.HideAndDontSave, wrapMode = TextureWrapMode.Clamp };
                        frames[i].LoadRawTextureData(g.Frames[i]);
                        frames[i].Apply(false, true);   // no longer readable: its copy in memory is let go
                    }
                }
                catch (Exception)   // the frames made so far are let go, not left behind
                {
                    Destroy(new Picture { Frames = frames });
                    return null;
                }
                return new Picture { Frames = frames, Timing = g.Frames.Count > 1 ? g : null, Bytes = (long)g.Width * g.Height * 4 * frames.Length };
            }
            if (item.Still == null) return null;
            var t = new Texture2D(2, 2) { hideFlags = HideFlags.HideAndDontSave };
            bool loaded;
            try { loaded = t.LoadImage(item.Still, false); } catch (Exception) { loaded = false; }
            if (!loaded) { UnityEngine.Object.DestroyImmediate(t); return null; }
            t = Smaller(t, StillSide);   // (a store's picture can be thousands of pixels across: kept at the size it's drawn)
            t.Apply(false, true);        // no longer readable: its copy in memory is let go
            return new Picture { Frames = new[] { t }, Bytes = (long)t.width * t.height * 4 };
        }

        /// <summary>A picture no bigger than side across, made on the graphics card; the one given when it's already
        /// small enough (or can't be made smaller). The bigger one is let go.</summary>
        static Texture2D Smaller(Texture2D t, int side)
        {
            if (t.width <= side && t.height <= side) return t;
            float k = Mathf.Min((float)side / t.width, (float)side / t.height);
            int w = Mathf.Max(1, Mathf.RoundToInt(t.width * k)), h = Mathf.Max(1, Mathf.RoundToInt(t.height * k));
            var was = RenderTexture.active;
            var rt = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            Texture2D small = null;
            try
            {
                t.filterMode = FilterMode.Bilinear;
                Graphics.Blit(t, rt);
                RenderTexture.active = rt;
                small = new Texture2D(w, h, TextureFormat.RGBA32, false)
                    { hideFlags = HideFlags.HideAndDontSave, wrapMode = TextureWrapMode.Clamp };
                small.ReadPixels(new Rect(0, 0, w, h), 0, 0, false);
                UnityEngine.Object.DestroyImmediate(t);
                return small;
            }
            catch (Exception)   // (kept as it is: larger, but shown)
            {
                if (small != null) UnityEngine.Object.DestroyImmediate(small);
                return t;
            }
            finally
            {
                RenderTexture.active = was;
                RenderTexture.ReleaseTemporary(rt);
            }
        }

        /// <summary>Free a picture's textures.</summary>
        static void Destroy(Picture p)
        {
            foreach (var t in p.Frames) if (t != null) UnityEngine.Object.DestroyImmediate(t);
        }

        /// <summary>Forget every picture (one being read is dropped when it arrives).</summary>
        public void Clear()
        {
            generation++;
            foreach (var p in ready.Values) Destroy(p);
            ready.Clear();
            shelf.Clear();
            Read item;
            while (read.TryDequeue(out item)) { }
        }
    }
}
