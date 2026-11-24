// mbtool: H3EK's ManagedBlam from a plain .NET Framework program (2026-11-23). Inside Python, ManagedBlam crashed on its
// "result < 1ull<<32" assertion; a native .NET process runs it fine. It edits what tool.exe can't:
//   - fields whose name appears twice in a layout (tool.exe resolves the first: a weapon barrel's "projectile" label
//     shadows its "projectile" tag reference, and a patch then changes nothing while reporting success)
//   - removing block elements (tool.exe can't change a block's size)
// ManagedBlam's field paths carry each field's type, e.g. "Block:barrels[0]/Reference:projectile".
// Build:  csc -platform:x64 -out:mbtool.exe -r:<H3EK>\bin\ManagedBlam.dll mbtool.cs
// usage:  mbtool <H3EK> paths  <tag path without extension> <extension>            every field, typed path = value
//         mbtool <H3EK> set    <tag> <ext> <typed field path> <value>             reference values: "path,extension"
//         mbtool <H3EK> add    <tag> <ext> <typed block path>                       appends one empty element
//         mbtool <H3EK> batch  <tag> <ext> <file>   lines "add\t<block>" ({N} = its new index), "set\t<path>\t<value>"
//         mbtool <H3EK> remove <tag> <ext> <typed block path> <element index>
// Every change is saved, then the tag is loaded again and the field read back; the exit code is 0 only if it matches.
using System;
using System.IO;
using System.Reflection;
using Bungie.Tags;

class Program
{
    static int Main(string[] args)
    {
        string ek = Path.GetFullPath(args[0]);
        Directory.SetCurrentDirectory(ek);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(ek, "bin", new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        return Run(ek, args);
    }
    static string Value(TagField f)
    {
        var r = f as TagFieldReference;
        if (r != null) return r.Path == null ? "" : r.Path.RelativePath + "," + r.Path.Extension;
        var e = f as TagFieldElement;
        if (e != null) { try { return e.GetStringData(); } catch { return "?"; } }
        var b = f as TagFieldBlock;
        if (b != null) return "block," + b.Elements.Count;
        var vp = f.GetType().GetProperty("Value");                      // block indices and the like: a Value property
        if (vp != null && vp.CanRead) { try { var v = vp.GetValue(f, null); return v == null ? "" : v.ToString(); } catch { return "?"; } }
        return "";
    }
    static bool SetByProperty(TagField f, string val)
    {
        var vp = f.GetType().GetProperty("Value");
        if (vp == null || !vp.CanWrite)
        {
            Console.WriteLine(f.GetType().Name + " has no settable Value; its properties:");
            foreach (var p in f.GetType().GetProperties()) Console.WriteLine("   " + p.PropertyType.Name + " " + p.Name + (p.CanWrite ? " (settable)" : ""));
            return false;
        }
        vp.SetValue(f, Convert.ChangeType(val, vp.PropertyType), null);
        return true;
    }
    static void Dump(TagField[] fields)
    {
        foreach (var f in fields)
        {
            Console.WriteLine(f.FieldPath + " = " + Value(f));
            var st = f as TagFieldStruct;
            if (st != null) foreach (var el in st.Elements) Dump(el.Fields);
            var b = f as TagFieldBlock;
            if (b != null) foreach (var el in b.Elements) Dump(el.Fields);
        }
    }
    static TagFile Load(string path, string ext)
    {
        var t = new TagFile(); t.Load(TagPath.FromPathAndExtension(path, ext)); return t;
    }
    static int Run(string ek, string[] a)
    {
        Bungie.ManagedBlamSystem.InitializeProject(Bungie.InitializationType.TagsOnly, ek);
        string cmd = a[1], path = a[2], ext = a[3];
        if (cmd == "paths")
        {
            using (var t = Load(path, ext)) Dump(t.Fields);
            return 0;
        }
        if (cmd == "set")
        {
            string fp = a[4], val = a[5];
            using (var t = Load(path, ext))
            {
                var f = t.SelectField(fp);
                if (f == null) { Console.WriteLine("no such field: " + fp); return 2; }
                var r = f as TagFieldReference;
                if (r != null)
                {
                    int c = val.LastIndexOf(',');
                    r.Path = val.Length == 0 ? null : TagPath.FromPathAndExtension(val.Substring(0, c), val.Substring(c + 1));
                }
                else
                {
                    var e = f as TagFieldElement;
                    if (e != null) { if (!e.SetStringData(val)) { Console.WriteLine("refused: " + val); return 3; } }
                    else if (!SetByProperty(f, val)) { Console.WriteLine("not a value field: " + fp + " (" + f.GetType().Name + ")"); return 2; }
                }
                t.Save();
            }
            using (var t = Load(path, ext))
            {
                string got = Value(t.SelectField(fp));
                Console.WriteLine(fp + " = " + got);
                return got.Equals(val, StringComparison.OrdinalIgnoreCase) ? 0 : 4;
            }
        }
        if (cmd == "batch")
        {
            // one load, many edits, one save: lines "add<TAB><block path>" (its new index becomes {N}) and
            // "set<TAB><typed path, may hold {N}><TAB><value>"; then every set is read back after a reload
            var lines = File.ReadAllLines(a[4]); var sets = new System.Collections.Generic.List<string[]>(); int last = -1;
            using (var t = Load(path, ext))
            {
                foreach (var raw in lines)
                {
                    if (raw.Trim().Length == 0) continue;
                    var p = raw.Split('\t');
                    if (p[0] == "add")
                    {
                        var b = t.SelectField(p[1]) as TagFieldBlock;
                        if (b == null) { Console.WriteLine("no such block: " + p[1]); return 2; }
                        last = b.Elements.Count; b.AddElement();
                    }
                    else if (p[0] == "set")
                    {
                        string fp = p[1].Replace("{N}", last.ToString()), val = p[2];
                        var f = t.SelectField(fp);
                        if (f == null) { Console.WriteLine("no such field: " + fp); return 2; }
                        var r = f as TagFieldReference; var e = f as TagFieldElement;
                        if (r != null) { int c = val.LastIndexOf(','); r.Path = val.Length == 0 ? null : TagPath.FromPathAndExtension(val.Substring(0, c), val.Substring(c + 1)); }
                        else if (e != null) { if (!e.SetStringData(val)) { Console.WriteLine("refused: " + fp + " = " + val); return 3; } }
                        else if (!SetByProperty(f, val)) { Console.WriteLine("not a value field: " + fp); return 2; }
                        sets.Add(new[] { fp, val });
                    }
                }
                t.Save();
            }
            int bad = 0;
            using (var t = Load(path, ext))
                foreach (var s in sets)
                {
                    string got = Value(t.SelectField(s[0]));
                    if (!got.Equals(s[1], StringComparison.OrdinalIgnoreCase)) { bad++; Console.WriteLine("read back " + s[0] + " = " + got + " (wanted " + s[1] + ")"); }
                }
            Console.WriteLine(sets.Count + " values set, " + (sets.Count - bad) + " read back");
            return bad == 0 ? 0 : 4;
        }
        if (cmd == "add")
        {
            string bp = a[4]; int before;
            using (var t = Load(path, ext))
            {
                var b = t.SelectField(bp) as TagFieldBlock;
                if (b == null) { Console.WriteLine("no such block: " + bp); return 2; }
                before = b.Elements.Count; b.AddElement(); t.Save();
            }
            using (var t = Load(path, ext))
            {
                int after = ((TagFieldBlock)t.SelectField(bp)).Elements.Count;
                Console.WriteLine(bp + ": " + before + " -> " + after + " elements (new one: [" + before + "])");
                return after == before + 1 ? 0 : 4;
            }
        }
        if (cmd == "remove")
        {
            string bp = a[4]; int idx = int.Parse(a[5]); int before;
            using (var t = Load(path, ext))
            {
                var b = t.SelectField(bp) as TagFieldBlock;
                if (b == null) { Console.WriteLine("no such block: " + bp); return 2; }
                before = b.Elements.Count; b.RemoveElement(idx); t.Save();
            }
            using (var t = Load(path, ext))
            {
                int after = ((TagFieldBlock)t.SelectField(bp)).Elements.Count;
                Console.WriteLine(bp + ": " + before + " -> " + after + " elements");
                return after == before - 1 ? 0 : 4;
            }
        }
        Console.WriteLine("unknown command " + cmd); return 1;
    }
}
