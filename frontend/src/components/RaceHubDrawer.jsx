import React, { useState, useEffect, useCallback } from 'react';
import {
  getRaceHubItems,
  createRaceHubItem,
  updateRaceHubItem,
  deleteRaceHubItem,
} from '../api.js';

const SECTIONS = [
  { id: 'fleet',      label: 'Fleet',      hint: 'Cars, spare parts, tools, setup notes' },
  { id: 'media',      label: 'Media',      hint: 'Shoots, projects, storage, camera assignments' },
  { id: 'monitoring', label: 'Monitoring', hint: 'Runbooks, dashboards, on-call notes' },
  { id: 'general',    label: 'General',    hint: 'Anything else' },
];

const STATUS_OPTIONS = [
  { id: 'unknown',   label: 'Unknown',    icon: '·' },
  { id: 'ok',        label: 'OK',         icon: '✓' },
  { id: 'attention', label: 'Attention',  icon: '⚠' },
];

const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map(s => [s.id, s]));

function emptyDraft(section) {
  return { section, title: '', detail: '', status: 'unknown', link_url: '' };
}

export default function RaceHubDrawer({ open, onClose }) {
  const [activeSection, setActiveSection] = useState('fleet');
  const [items,         setItems]         = useState([]);
  const [loading,       setLoading]       = useState(false);
  const [draft,         setDraft]         = useState(emptyDraft('fleet'));
  const [editingId,     setEditingId]     = useState(null);
  const [editing,       setEditing]       = useState(null);
  const [msg,           setMsg]           = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getRaceHubItems();
      setItems(data.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    load();
  }, [open, load]);

  useEffect(() => {
    setDraft(d => ({ ...d, section: activeSection }));
  }, [activeSection]);

  function flash(text) {
    setMsg(text);
    setTimeout(() => setMsg(''), 2000);
  }

  async function handleAdd() {
    const title = draft.title.trim();
    if (!title) {
      flash('Title required');
      return;
    }
    try {
      await createRaceHubItem({ ...draft, title });
      setDraft(emptyDraft(activeSection));
      flash('Added');
      load();
    } catch {
      flash('Add failed');
    }
  }

  async function handleDelete(id) {
    await deleteRaceHubItem(id);
    if (editingId === id) {
      setEditingId(null);
      setEditing(null);
    }
    load();
  }

  function startEdit(item) {
    setEditingId(item.id);
    setEditing({
      section:  item.section,
      title:    item.title,
      detail:   item.detail || '',
      status:   item.status,
      link_url: item.link_url || '',
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditing(null);
  }

  async function saveEdit() {
    if (!editing) return;
    const title = editing.title.trim();
    if (!title) {
      flash('Title required');
      return;
    }
    await updateRaceHubItem(editingId, { ...editing, title });
    setEditingId(null);
    setEditing(null);
    flash('Saved');
    load();
  }

  async function cycleStatus(item) {
    const order = ['unknown', 'ok', 'attention'];
    const next  = order[(order.indexOf(item.status) + 1) % order.length];
    await updateRaceHubItem(item.id, { status: next });
    load();
  }

  const sectionItems = items.filter(i => i.section === activeSection);
  const counts = SECTIONS.reduce((acc, s) => {
    const list = items.filter(i => i.section === s.id);
    acc[s.id] = {
      total:     list.length,
      attention: list.filter(i => i.status === 'attention').length,
    };
    return acc;
  }, {});
  const activeMeta = SECTIONS.find(s => s.id === activeSection);

  return (
    <div id="race-hub" className={open ? 'open' : ''}>
      <div id="race-hub-close">
        <span>Racing & Media Ops</span>
        <button onClick={onClose} title="Close">&#x2715;</button>
      </div>

      <div className="rh-tabs">
        {SECTIONS.map(s => {
          const c = counts[s.id] || { total: 0, attention: 0 };
          return (
            <button
              key={s.id}
              className={'rh-tab' + (activeSection === s.id ? ' active' : '')}
              onClick={() => setActiveSection(s.id)}
            >
              <span className="rh-tab-label">{s.label}</span>
              <span className="rh-tab-count">{c.total}</span>
              {c.attention > 0 && <span className="rh-tab-attn" title={`${c.attention} need attention`}>!</span>}
            </button>
          );
        })}
      </div>

      <div className="rh-hint">{activeMeta?.hint}</div>

      {activeSection === 'monitoring' && (
        <div className="rh-callout">
          Live host metrics live in <strong>Settings → SSH Hosts</strong>. Use this section
          for runbooks, dashboard URLs, and on-call notes.
        </div>
      )}

      <div className="rh-list">
        {loading && <div className="rh-empty">Loading…</div>}
        {!loading && sectionItems.length === 0 && (
          <div className="rh-empty">No items yet — add one below.</div>
        )}
        {!loading && sectionItems.map(item => {
          const isEditing = editingId === item.id;
          const status = STATUS_LABEL[item.status] || STATUS_LABEL.unknown;
          if (isEditing && editing) {
            return (
              <div key={item.id} className="rh-item editing">
                <div className="sg">
                  <label>Title</label>
                  <input
                    value={editing.title}
                    onChange={e => setEditing({ ...editing, title: e.target.value })}
                  />
                </div>
                <div className="sg">
                  <label>Detail</label>
                  <textarea
                    rows="2"
                    value={editing.detail}
                    onChange={e => setEditing({ ...editing, detail: e.target.value })}
                  />
                </div>
                <div className="srow">
                  <select
                    value={editing.section}
                    onChange={e => setEditing({ ...editing, section: e.target.value })}
                  >
                    {SECTIONS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                  </select>
                  <select
                    value={editing.status}
                    onChange={e => setEditing({ ...editing, status: e.target.value })}
                  >
                    {STATUS_OPTIONS.map(s => (
                      <option key={s.id} value={s.id}>{s.icon} {s.label}</option>
                    ))}
                  </select>
                </div>
                <div className="sg">
                  <label>Link URL</label>
                  <input
                    value={editing.link_url}
                    placeholder="https://…"
                    onChange={e => setEditing({ ...editing, link_url: e.target.value })}
                  />
                </div>
                <div className="srow">
                  <button className="sbtn p" onClick={saveEdit}>Save</button>
                  <button className="sbtn"   onClick={cancelEdit}>Cancel</button>
                </div>
              </div>
            );
          }
          return (
            <div key={item.id} className={'rh-item status-' + item.status}>
              <button
                className={'rh-status status-' + item.status}
                onClick={() => cycleStatus(item)}
                title={`Status: ${status.label} (click to cycle)`}
              >
                {status.icon}
              </button>
              <div className="rh-body">
                <div className="rh-title">{item.title}</div>
                {item.detail && <div className="rh-detail">{item.detail}</div>}
                {item.link_url && (
                  <a
                    className="rh-link"
                    href={item.link_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {item.link_url}
                  </a>
                )}
              </div>
              <div className="rh-actions">
                <button onClick={() => startEdit(item)} title="Edit">✎</button>
                <button onClick={() => handleDelete(item.id)} title="Delete">&times;</button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="rh-add">
        <h3>Add to {activeMeta?.label}</h3>
        <div className="sg">
          <label>Title</label>
          <input
            placeholder={activeSection === 'fleet'      ? 'e.g. Front-right tire — replace before next race'
                       : activeSection === 'media'      ? 'e.g. GoPro 7 — assigned to driver cam'
                       : activeSection === 'monitoring' ? 'e.g. Pit-wall Grafana dashboard'
                       :                                  'Title'}
            value={draft.title}
            onChange={e => setDraft({ ...draft, title: e.target.value })}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(); }}
          />
        </div>
        <div className="sg">
          <label>Detail (optional)</label>
          <textarea
            rows="2"
            value={draft.detail}
            onChange={e => setDraft({ ...draft, detail: e.target.value })}
          />
        </div>
        <div className="srow">
          <select
            value={draft.status}
            onChange={e => setDraft({ ...draft, status: e.target.value })}
          >
            {STATUS_OPTIONS.map(s => (
              <option key={s.id} value={s.id}>{s.icon} {s.label}</option>
            ))}
          </select>
          <input
            style={{ flex: 1, minWidth: 0 }}
            placeholder="Link URL (optional)"
            value={draft.link_url}
            onChange={e => setDraft({ ...draft, link_url: e.target.value })}
          />
        </div>
        <div className="srow">
          <button className="sbtn p" onClick={handleAdd}>Add Item</button>
          {msg && <span className="sv-msg">{msg}</span>}
        </div>
      </div>
    </div>
  );
}
