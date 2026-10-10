// What a .zip holds, and one of its files to read: enough to find the .unitypackage files a product came zipped in
// and read or unpack one, without System.IO.Compression's ZipArchive (which a project on the .NET Framework profile
// doesn't reference). Stored and deflated files, ZIP64 included. Plain C#, no Unity references.
//
// A zip is a file anyone could have made, so what it claims is checked before it's acted on: every size and place
// must fall inside the file, names are read with a limit, and a file is checked against its CRC as it's unpacked.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace SoloFlighter.Hoard
{
    public sealed class ZipEntry
    {
        public string Name;
        public long Size, CompressedSize, LocalOffset;
        public int Method;
        public uint Crc;
        public bool Locked;   // encrypted: it can't be read without its password
    }

    public static class ZipReader
    {
        const int MaxEntries = 100000;
        const uint EndSig = 0x06054b50, CentralSig = 0x02014b50, LocalSig = 0x04034b50, Zip64EndSig = 0x06064b50, Zip64LocatorSig = 0x07064b50;

        /// <summary>Every file in the zip (not its folders). Throws InvalidDataException if it isn't one.</summary>
        public static List<ZipEntry> List(Stream s)
        {
            long length = s.Length;
            // the end record: in the last 22 bytes, or before a comment of up to 64 KB
            int tail = (int)Math.Min(length, 22 + 65535);
            var buf = new byte[tail];
            s.Position = length - tail;
            ReadFull(s, buf, tail);
            int end = -1;
            for (int i = tail - 22; i >= 0; i--)
                if (U32(buf, i) == EndSig) { end = i; break; }
            if (end < 0) throw new InvalidDataException("not a zip");
            long count = U16(buf, end + 10), cdSize = U32(buf, end + 12), cdOffset = U32(buf, end + 16);
            if (count == 0xFFFF || cdSize == 0xFFFFFFFF || cdOffset == 0xFFFFFFFF)   // ZIP64: the real numbers are elsewhere
            {
                long locator = length - tail + end - 20;
                if (locator < 0) throw new InvalidDataException("not a zip");
                var loc = new byte[20];
                s.Position = locator;
                ReadFull(s, loc, 20);
                if (U32(loc, 0) != Zip64LocatorSig) throw new InvalidDataException("not a zip");
                long at = (long)U64(loc, 8);
                if (at < 0 || at + 56 > length) throw new InvalidDataException("not a zip");
                var rec = new byte[56];
                s.Position = at;
                ReadFull(s, rec, 56);
                if (U32(rec, 0) != Zip64EndSig) throw new InvalidDataException("not a zip");
                count = (long)U64(rec, 32); cdSize = (long)U64(rec, 40); cdOffset = (long)U64(rec, 48);
            }
            if (count < 0 || count > MaxEntries || cdOffset < 0 || cdSize < 0 || cdOffset + cdSize > length || cdSize > 64L << 20)
                throw new InvalidDataException("not a zip");
            var cd = new byte[cdSize];
            s.Position = cdOffset;
            ReadFull(s, cd, (int)cdSize);
            var list = new List<ZipEntry>();
            int p = 0;
            for (long n = 0; n < count; n++)
            {
                if (p + 46 > cd.Length || U32(cd, p) != CentralSig) throw new InvalidDataException("not a zip");
                int flags = U16(cd, p + 8), nameLen = U16(cd, p + 28), extraLen = U16(cd, p + 30), commentLen = U16(cd, p + 32);
                if (p + 46 + nameLen + extraLen + commentLen > cd.Length) throw new InvalidDataException("not a zip");
                var e = new ZipEntry
                {
                    Method = U16(cd, p + 10), Crc = U32(cd, p + 16), CompressedSize = U32(cd, p + 20), Size = U32(cd, p + 24),
                    LocalOffset = U32(cd, p + 42), Locked = (flags & 1) != 0,
                    Name = DecodeName(cd, p + 46, nameLen, (flags & 0x800) != 0),
                };
                ReadZip64(cd, p + 46 + nameLen, extraLen, e);
                if (e.Size < 0 || e.CompressedSize < 0 || e.LocalOffset < 0 || e.LocalOffset + 30 + e.CompressedSize > length)
                    throw new InvalidDataException("not a zip");
                if (!e.Name.EndsWith("/")) list.Add(e);
                p += 46 + nameLen + extraLen + commentLen;
            }
            return list;
        }

        /// <summary>One file's contents, as it's read: a stream that ends where the file does.</summary>
        public static Stream Open(Stream s, ZipEntry e)
        {
            if (e.Locked) throw new InvalidDataException("it's locked with a password");
            if (e.Method != 0 && e.Method != 8) throw new InvalidDataException("it's packed in a way Hoard can't read");
            var local = new byte[30];
            s.Position = e.LocalOffset;
            ReadFull(s, local, 30);
            if (U32(local, 0) != LocalSig) throw new InvalidDataException("not a zip");
            long data = e.LocalOffset + 30 + U16(local, 26) + U16(local, 28);
            if (data + e.CompressedSize > s.Length) throw new InvalidDataException("not a zip");
            var part = new Part(s, data, e.CompressedSize);
            return e.Method == 0 ? (Stream)part : new DeflateStream(part, CompressionMode.Decompress);
        }

        /// <summary>Copy one file out of the zip, checking it against its CRC; the copy is no larger than the zip says.</summary>
        public static void CopyTo(Stream zip, ZipEntry e, Stream into)
        {
            using (var from = Open(zip, e))
            {
                var buf = new byte[1 << 16];
                long left = e.Size;
                uint crc = 0xFFFFFFFF;
                int r;
                while ((r = from.Read(buf, 0, (int)Math.Min(buf.Length, Math.Max(left, 1)))) > 0)
                {
                    if (r > left) throw new InvalidDataException("it's larger than the zip says");
                    for (int i = 0; i < r; i++) crc = Table[(crc ^ buf[i]) & 0xFF] ^ (crc >> 8);
                    into.Write(buf, 0, r);
                    left -= r;
                }
                if (left != 0 || (crc ^ 0xFFFFFFFF) != e.Crc) throw new InvalidDataException("it's damaged");
            }
        }

        static void ReadZip64(byte[] b, int at, int len, ZipEntry e)
        {
            int end = at + len;
            while (at + 4 <= end)
            {
                int id = U16(b, at), size = U16(b, at + 2), p = at + 4;
                if (p + size > end) return;
                if (id == 1)
                {
                    if (e.Size == 0xFFFFFFFF && p + 8 <= at + 4 + size) { e.Size = (long)U64(b, p); p += 8; }
                    if (e.CompressedSize == 0xFFFFFFFF && p + 8 <= at + 4 + size) { e.CompressedSize = (long)U64(b, p); p += 8; }
                    if (e.LocalOffset == 0xFFFFFFFF && p + 8 <= at + 4 + size) { e.LocalOffset = (long)U64(b, p); }
                    return;
                }
                at += 4 + size;
            }
        }

        /// <summary>A name as its maker wrote it: UTF-8 when the zip says so, or when it is; else Shift-JIS, as most
        /// zips made on a Japanese computer are, where this editor can read that; else as bytes, unchanged.</summary>
        static string DecodeName(byte[] b, int at, int len, bool utf8)
        {
            if (utf8) return Encoding.UTF8.GetString(b, at, len);
            try { return new UTF8Encoding(false, true).GetString(b, at, len); }
            catch (DecoderFallbackException) { }
            try { return Encoding.GetEncoding(932, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback).GetString(b, at, len); }
            catch (Exception) { }
            var chars = new char[len];
            for (int i = 0; i < len; i++) chars[i] = (char)b[at + i];
            return new string(chars);
        }

        static readonly uint[] Table = MakeTable();
        static uint[] MakeTable()
        {
            var t = new uint[256];
            for (uint n = 0; n < 256; n++)
            {
                uint c = n;
                for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
                t[n] = c;
            }
            return t;
        }

        static int U16(byte[] b, int at) { return b[at] | b[at + 1] << 8; }
        static uint U32(byte[] b, int at) { return (uint)(b[at] | b[at + 1] << 8 | b[at + 2] << 16 | b[at + 3] << 24); }
        static ulong U64(byte[] b, int at) { return U32(b, at) | (ulong)U32(b, at + 4) << 32; }

        static void ReadFull(Stream s, byte[] buf, int n)
        {
            int got = 0;
            while (got < n)
            {
                int r = s.Read(buf, got, n - got);
                if (r <= 0) throw new InvalidDataException("the zip ends partway");
                got += r;
            }
        }

        /// <summary>Part of a stream, read from start for length bytes, and nothing past it.</summary>
        sealed class Part : Stream
        {
            readonly Stream inner;
            long at, left;
            public Part(Stream inner, long start, long length) { this.inner = inner; at = start; left = length; }
            public override int Read(byte[] buffer, int offset, int count)
            {
                if (left <= 0) return 0;
                inner.Position = at;
                int r = inner.Read(buffer, offset, (int)Math.Min(count, left));
                if (r <= 0) throw new InvalidDataException("the zip ends partway");
                at += r; left -= r;
                return r;
            }
            public override bool CanRead { get { return true; } }
            public override bool CanSeek { get { return false; } }
            public override bool CanWrite { get { return false; } }
            public override long Length { get { throw new NotSupportedException(); } }
            public override long Position { get { throw new NotSupportedException(); } set { throw new NotSupportedException(); } }
            public override void Flush() { }
            public override long Seek(long offset, SeekOrigin origin) { throw new NotSupportedException(); }
            public override void SetLength(long value) { throw new NotSupportedException(); }
            public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
        }
    }
}
