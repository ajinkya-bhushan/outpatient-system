import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';

/**
 * One speaker turn in the transcript.
 *
 * Playback is driven from outside: the screen owns a single <audio> element and
 * seeks it, so a bubble only reports intent through `onPlay` and renders the
 * `isPlaying` state it is handed back. Editing is local until saved.
 */
function TranscriptBubble({
  speaker,
  doctor = false,
  children,
  text,
  timeLabel,
  canPlay = false,
  isPlaying = false,
  editable = false,
  onPlay,
  onEditSave,
}) {
  const body = text ?? children;
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(typeof body === 'string' ? body : '');
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!isEditing && typeof body === 'string') {
      setDraft(body);
    }
  }, [body, isEditing]);

  useEffect(() => {
    if (isEditing) {
      textareaRef.current?.focus();
      textareaRef.current?.select();
    }
  }, [isEditing]);

  const save = () => {
    const next = draft.trim();
    if (next && next !== body) {
      onEditSave?.(next);
    }
    setIsEditing(false);
  };

  const cancel = () => {
    setDraft(typeof body === 'string' ? body : '');
    setIsEditing(false);
  };

  const hasActions = (canPlay && onPlay) || (editable && onEditSave);

  return (
    <article className={`transcript-bubble ${doctor ? 'doctor' : ''}`}>
      <span className="transcript-bubble-speaker">
        {speaker}
        {timeLabel ? <em className="transcript-bubble-time">{timeLabel}</em> : null}
      </span>

      {isEditing ? (
        <div className="turn-editor">
          <textarea
            ref={textareaRef}
            value={draft}
            rows={Math.min(8, Math.max(2, Math.ceil(draft.length / 60)))}
            aria-label={`Edit what ${speaker} said`}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                cancel();
              }
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                save();
              }
            }}
          />
          <div className="turn-editor-actions">
            <button type="button" className="button button-soft button-tiny" onClick={cancel}>
              Cancel
            </button>
            <button type="button" className="button button-primary button-tiny" onClick={save}>
              Save
            </button>
          </div>
        </div>
      ) : (
        <p>{body}</p>
      )}

      {hasActions && !isEditing ? (
        <div className="turn-actions">
          {canPlay && onPlay ? (
            <button
              type="button"
              className={`turn-action-button ${isPlaying ? 'active' : ''}`}
              onClick={onPlay}
              aria-label={isPlaying ? 'Stop playback' : `Play what ${speaker} said`}
              title={isPlaying ? 'Stop playback' : 'Play this turn'}
            >
              <Icon name={isPlaying ? 'stop_circle' : 'play_arrow'} filled />
            </button>
          ) : null}
          {editable && onEditSave ? (
            <button
              type="button"
              className="turn-action-button"
              onClick={() => setIsEditing(true)}
              aria-label={`Edit what ${speaker} said`}
              title="Edit this turn"
            >
              <Icon name="edit" />
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export default TranscriptBubble;
