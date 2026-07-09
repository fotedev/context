import React, { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import { InputFile } from '../../shared/types';

/** Lists .context/inputs/*.txt, create-from-textarea, paste-from-clipboard, delete.
 *
 * Reads InputsResponse.items (NOT a bare list — gap 6) and renders
 * InputsResponse.message ("No input files found") when empty (edge 9).
 */
const InputManager: React.FC = () => {
  const [inputs, setInputs] = useState<InputFile[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState('');
  const [showForm, setShowForm] = useState(false);

  const loadInputs = async () => {
    try {
      const res = await api.getInputs();
      setInputs(res.items);
      setMessage(res.message);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    loadInputs();
  }, []);

  const handleCreate = async () => {
    try {
      await api.createInput(newName, newContent);
      setNewName('');
      setNewContent('');
      setShowForm(false);
      loadInputs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setNewContent(text);
      setMessage('Pasted from clipboard.');
    } catch {
      setMessage('Failed to read clipboard.');
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await api.deleteInput(name);
      loadInputs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div style={{ marginTop: '15px', padding: '10px', border: '1px solid #ddd' }}>
      <h4>Inputs</h4>
      {message && (
        <div style={{ fontSize: '12px', color: 'blue', marginBottom: '10px' }}>{message}</div>
      )}

      <ul style={{ listStyleType: 'none', padding: 0, margin: 0 }}>
        {inputs.map((inp) => (
          <li
            key={inp.name}
            style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}
          >
            <span>
              {inp.name}.txt{' '}
              {inp.source === 'cwd-fallback' && <em>(CWD fallback)</em>}
            </span>
            <button onClick={() => handleDelete(inp.name)}>Delete</button>
          </li>
        ))}
      </ul>

      <button onClick={() => setShowForm(!showForm)}>
        {showForm ? 'Cancel' : 'New Input'}
      </button>

      {showForm && (
        <div style={{ marginTop: '10px' }}>
          <input
            type="text"
            placeholder="Input name (e.g. fix-navbar)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ width: '100%', marginBottom: '5px', boxSizing: 'border-box' }}
          />
          <textarea
            placeholder="File paths or content..."
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            style={{ width: '100%', height: '100px', marginBottom: '5px', boxSizing: 'border-box' }}
          />
          <button onClick={handlePasteClipboard} style={{ marginRight: '5px' }}>
            Paste from Clipboard
          </button>
          <button onClick={handleCreate} disabled={!newName}>
            Create Input
          </button>
        </div>
      )}
    </div>
  );
};

export default InputManager;
