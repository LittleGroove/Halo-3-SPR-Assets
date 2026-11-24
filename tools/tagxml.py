# Reads an H3EK `tool export-tag-to-xml` file into the field paths `tool get-tag-field-value` / `patch-tag-field`
# take, with each field's type and value, in the file's order.
# The XML's blocks are elements (<block name=".." value="type,count"> <element index="k"> ...), but a struct is a
# self-closing <field type="struct"/> whose members follow it as siblings, deeper indented: so this reads the lines and
# their indentation, not the XML tree. Paths: "<group>_group[0].unit[0].seats[3].unit camera[0].pitch range".
# A flags field's set bits are the indented lines inside it; enums give their label as the value.
# usage (as a tool): python -I tagxml.py <file.xml> [filter]
import re, sys, html
LINE = re.compile(r'^(\s*)<(/?)(field|block|element|tag)\b([^>]*?)(/?)>(.*)$')
ATTR = re.compile(r'(\w+)="([^"]*)"')
def read(path):
    """[(tool path, type, value, extra)] in file order; extra = the set bit names for flags."""
    out = []; stack = []                       # entries: (indent, path-part) for structs, blocks and elements
    root = None; pending_flags = None
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    for raw in lines:
        m = LINE.match(raw)
        if not m:
            if pending_flags is not None and raw.strip() and not raw.strip().startswith('<'):
                pending_flags[3].append(html.unescape(raw.strip()))
            continue
        ind, close, kind, attrs, selfclose, rest = len(m.group(1).expandtabs(4)), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        a = {k: html.unescape(v) for k, v in ATTR.findall(attrs)}
        if kind == 'tag' and not close:
            root = a.get('group', 'tag') + '_group[0]'; continue
        if close:
            if kind in ('block', 'element'):
                while stack and stack[-1][2] != kind: stack.pop()
                if stack: stack.pop()
            if kind == 'field': pending_flags = None
            continue
        while stack and stack[-1][2] == 'struct' and stack[-1][0] >= ind: stack.pop()
        # a block's name is replaced by its element's "name[k]" once inside an element
        base = '.'.join([root] + [s[1] for k, s in enumerate(stack)
                                  if not (s[2] == 'block' and k + 1 < len(stack) and stack[k + 1][2] == 'element')])
        if kind == 'element':
            blk = stack[-1][1] if stack and stack[-1][2] == 'block' else '?'
            stack.append((ind, f"{blk}[{a.get('index')}]", 'element')); continue
        if kind == 'block':
            out.append((f"{base}.{a['name']}", 'block', a.get('value', ''), None))
            stack.append((ind, a['name'], 'block')); continue
        t = a.get('type', ''); name = a.get('name', '')
        if t == 'struct':
            out.append((f"{base}.{name}", 'struct', '', None)); stack.append((ind, f"{name}[0]", 'struct')); continue
        entry = (f"{base}.{name}", t, a.get('value', ''), [] if 'flags' in t else None)
        out.append(entry)
        pending_flags = entry if ('flags' in t and not selfclose) else None
    return out
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    rows = read(sys.argv[1]); flt = sys.argv[2].lower() if len(sys.argv) > 2 else ''
    print(len(rows), 'fields')
    for p, t, v, x in rows:
        if flt in p.lower(): print(p, '|', t, '|', v, ('| ' + ', '.join(x)) if x else '')
