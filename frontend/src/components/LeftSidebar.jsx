import React, { useState } from 'react';
import { createTopic, deleteTopic, activateTopic, getTopics } from '../api.js';
import ActivityPanel from './ActivityPanel.jsx';
import { toast } from '../lib/toast.js';

export default function LeftSidebar({ topics, onTopicsChange }) {
  const [inputVal, setInputVal] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const data = await getTopics();
      onTopicsChange(data.topics || []);
    } catch {}
  }

  async function handleAdd() {
    const val = inputVal.trim();
    if (!val || busy) return;
    setBusy(true);
    try {
      await createTopic(val);
      setInputVal('');
      await refresh();
      toast.success(`Added topic “${val}”`, 'Topics');
    } catch {
      toast.error('Could not create topic.', 'Topics');
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id, e) {
    e.stopPropagation();
    try {
      await deleteTopic(id);
      await refresh();
    } catch {
      toast.error('Could not delete topic.', 'Topics');
    }
  }

  async function handleActivate(id) {
    try {
      await activateTopic(id);
      await refresh();
    } catch {}
  }

  async function handleClearActive() {
    const active = topics.find(t => t.active);
    if (active) {
      await activateTopic(active.id);
      await refresh();
    }
  }

  const activeTopic = topics.find(t => t.active);

  return (
    <div id="sidebar-left">
      <div id="topics-section">
        <div className="sb-header">
          <span>
            Topics
            {topics.length > 0 && (
              <span style={{ color: 'var(--muted-2)', marginLeft: 6, fontWeight: 500 }}>
                · {topics.length}
              </span>
            )}
          </span>
          {activeTopic && (
            <button
              onClick={handleClearActive}
              title={`Clear active topic (${activeTopic.title})`}
              aria-label="Clear active topic"
            >
              ✕
            </button>
          )}
        </div>
        <div id="topics-list">
          {topics.length === 0 ? (
            <div style={{
              padding: '14px 16px', color: 'var(--muted-2)',
              fontSize: 11, fontStyle: 'italic', textAlign: 'center',
            }}>
              No topics yet — add one below to give Jarvis ongoing context.
            </div>
          ) : (
            topics.map(t => (
              <div
                key={t.id}
                className={'topic-item' + (t.active ? ' active' : '')}
                onClick={() => handleActivate(t.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleActivate(t.id);
                  }
                }}
              >
                <div className="topic-dot" />
                <div className="topic-body">
                  <div className="topic-title">{t.title}</div>
                  {t.description && (
                    <div className="topic-desc">{t.description}</div>
                  )}
                </div>
                <button
                  className="topic-del"
                  onClick={(e) => handleDelete(t.id, e)}
                  title="Remove topic"
                  aria-label={`Remove topic ${t.title}`}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
        <div id="topic-add">
          <input
            placeholder="Add topic…"
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(); }}
            aria-label="New topic"
          />
          <button onClick={handleAdd} disabled={busy || !inputVal.trim()} title="Add topic">
            +
          </button>
        </div>
      </div>

      <ActivityPanel />
    </div>
  );
}
