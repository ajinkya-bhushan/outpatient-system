const HEADING_RE = /^(#{1,6})\s+(.+?)\s*$/;
const HR_RE = /^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/;
const ORDERED_RE = /^(\s*)(\d+)\.\s+(.*)$/;
const BULLET_RE = /^(\s*)([-*+])\s+(.*)$/;

function listMatch(line) {
  const ordered = line.match(ORDERED_RE);
  if (ordered) {
    return { ordered: true, indent: ordered[1].length, text: ordered[3] };
  }
  const bullet = line.match(BULLET_RE);
  if (bullet) {
    return { ordered: false, indent: bullet[1].length, text: bullet[3] };
  }
  return null;
}

export function parseInline(text) {
  const nodes = [];
  let cursor = 0;

  while (cursor < text.length) {
    const boldAt = text.indexOf('**', cursor);
    if (boldAt === -1) {
      nodes.push({ type: 'text', text: text.slice(cursor) });
      break;
    }
    const boldEnd = text.indexOf('**', boldAt + 2);
    if (boldEnd === -1) {
      nodes.push({ type: 'text', text: text.slice(cursor) });
      break;
    }
    if (boldAt > cursor) {
      nodes.push({ type: 'text', text: text.slice(cursor, boldAt) });
    }
    nodes.push({ type: 'strong', text: text.slice(boldAt + 2, boldEnd) });
    cursor = boldEnd + 2;
  }

  return nodes.filter((node) => node.text !== '');
}

function consumeList(lines, start) {
  const items = [];
  let index = start;

  while (index < lines.length) {
    const item = listMatch(lines[index]);
    if (item) {
      items.push(item);
      index += 1;
      continue;
    }
    if (
      items.length
      && /^\s+\S/.test(lines[index])
      && !HEADING_RE.test(lines[index])
      && !HR_RE.test(lines[index])
    ) {
      items[items.length - 1].text = `${items[items.length - 1].text} ${lines[index].trim()}`;
      index += 1;
      continue;
    }
    break;
  }

  return { items, next: index };
}

function nestListItems(items, start, end, indent) {
  const children = [];
  let index = start;

  while (index < end) {
    const item = items[index];
    if (item.indent < indent) {
      break;
    }

    let nestedEnd = index + 1;
    while (nestedEnd < end && items[nestedEnd].indent > item.indent) {
      nestedEnd += 1;
    }

    children.push({
      type: 'listItem',
      children: [
        ...parseInline(item.text),
        ...(nestedEnd > index + 1
          ? [nestList(items, index + 1, nestedEnd, items[index + 1].indent)]
          : []),
      ],
    });
    index = nestedEnd;
  }

  return children;
}

function nestList(items, start, end, indent) {
  return {
    type: 'list',
    ordered: Boolean(items[start]?.ordered),
    children: nestListItems(items, start, end, indent),
  };
}

export function parseNoteMarkdown(text) {
  const source = text ?? '';
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (HR_RE.test(line)) {
      blocks.push({ type: 'hr' });
      index += 1;
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) {
      blocks.push({ type: 'heading', children: parseInline(heading[2]) });
      index += 1;
      continue;
    }

    if (listMatch(line)) {
      const list = consumeList(lines, index);
      if (list.items.length) {
        blocks.push(nestList(list.items, 0, list.items.length, list.items[0].indent));
      }
      index = list.next;
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !HEADING_RE.test(lines[index])
      && !HR_RE.test(lines[index])
      && !listMatch(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push({ type: 'paragraph', children: parseInline(paragraph.join(' ')) });
  }

  return blocks;
}
