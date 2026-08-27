import React from 'react';
import Icon from './Icon.jsx';
import { parseNoteMarkdown } from './noteMarkdown.js';

function renderInline(nodes, keyPrefix) {
  return nodes.map((node, index) => {
    const key = `${keyPrefix}-${index}`;
    if (node.type === 'strong') {
      return <strong key={key}>{node.text}</strong>;
    }
    return <React.Fragment key={key}>{node.text}</React.Fragment>;
  });
}

function renderBlocks(blocks, keyPrefix) {
  return blocks.map((block, index) => {
    const key = `${keyPrefix}-${index}`;
    if (block.type === 'heading') {
      return <h2 key={key}>{renderInline(block.children, key)}</h2>;
    }
    if (block.type === 'paragraph') {
      return <p key={key}>{renderInline(block.children, key)}</p>;
    }
    if (block.type === 'hr') {
      return <hr key={key} />;
    }
    if (block.type === 'list') {
      const ListTag = block.ordered ? 'ol' : 'ul';
      return (
        <ListTag className="review-note-list" key={key}>
          {block.children.map((item, itemIndex) => (
            <li key={`${key}-i${itemIndex}`}>
              {item.children.map((child, childIndex) => {
                if (child.type === 'list') {
                  return (
                    <React.Fragment key={`${key}-i${itemIndex}-n${childIndex}`}>
                      {renderBlocks([child], `${key}-i${itemIndex}-n${childIndex}`)}
                    </React.Fragment>
                  );
                }
                if (child.type === 'strong') {
                  return <strong key={`${key}-i${itemIndex}-s${childIndex}`}>{child.text}</strong>;
                }
                return <React.Fragment key={`${key}-i${itemIndex}-t${childIndex}`}>{child.text}</React.Fragment>;
              })}
            </li>
          ))}
        </ListTag>
      );
    }
    return null;
  });
}

export function NoteMarkdown({ text }) {
  const blocks = parseNoteMarkdown(text);
  if (!blocks.length) {
    return <p>{text || ''}</p>;
  }
  return <div className="review-note-markdown">{renderBlocks(blocks, 'n')}</div>;
}

function ReviewNoteCard({ title, icon, action, markdown, children }) {
  return (
    <section className="review-note-card">
      <header>
        <h2><Icon name={icon} />{title}</h2>
        {action}
      </header>
      <div className="review-note-body">
        {markdown != null ? <NoteMarkdown text={markdown} /> : null}
        {children}
      </div>
    </section>
  );
}

export default ReviewNoteCard;
