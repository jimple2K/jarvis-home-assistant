import React, { useState } from 'react';
import { createTopic, deleteTopic, activateTopic, getTopics } from '../api.js';
import ActivityPanel from './ActivityPanel.jsx';

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export default function LeftSidebar({ topics, onTopicsChange }) {
  const [inputVal, setInputVal] = useState('');

  async function handleAdd() {
    const val = inputVal.trim();
    if (!val) return;
    await createTopic(val);
    setInputVal('');
    const data = await getTopics();
    onTopicsChange(data.topics || []);
  }

  async function handleDelete(id, e) {
    e.stopPropagation();
    await deleteTopic(id);
    const data = await getTopics();
    onTopicsChange(data.topics || []);
  }

  async function handleActivate(id) {
    await activateTopic(id);
    const data = await getTopics();
    onTopicsChange(data.topics || []);
  }

  async function handleClearActive() {
    const active = topics.find(t => t.active);
    if (active) {
      await activateTopic(active.id);
      const data = await getTopics();
      onTopicsChange(data.topics || []);
    }
  }

  return (
    <div id="sidebar-left">
      <div id="topics-section">
        <div className="sb-header">
          Topics
          <button onClick={handleClearActive} title="Clear active topic">&#x2715;</button>
        </div>
        <div id="topics-list">
          {topics.map(t => (
            <div
              key={t.id}
              className={'topic-item' + (t.active ? ' active' : '')}
              onClick={() => handleActivate(t.id)}
            >
              <div className="topic-dot" />
              <div className="topic-body">
                <div
                  className="topic-title"
                  dangerouslySetInnerHTML={{ __html: esc(t.title) }}
                />
                {t.description && (
                  <div
                    className="topic-desc"
                    dangerouslySetInnerHTML={{ __html: esc(t.description) }}
                  />
                )}
              </div>
              <button
                className="topic-del"
                onClick={(e) => handleDelete(t.id, e)}
                title="Remove"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
        <div id="topic-add">
          <input
            placeholder="Add topic…"
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(); }}
          />
          <button onClick={handleAdd}>+</button>
        </div>
      </div>

      <ActivityPanel />
    </div>
  );
}
