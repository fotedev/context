import React, { useState } from 'react';
import { api } from '../../shared/api';

interface PairDialogProps {
  onPaired: () => void;
}

/** Paste a pairing code from the terminal to obtain a bearer token.
 *
 * The server prints the code on startup (`python aggregator.py --serve`);
 * the user pastes it here. On success the token is stored in
 * chrome.storage.local by api.pair().
 */
const PairDialog: React.FC<PairDialogProps> = ({ onPaired }) => {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handlePair = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.pair(code);
      onPaired();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '10px', border: '1px solid #ccc', marginTop: '10px' }}>
      <h4>Pair with Server</h4>
      <p>Enter the pairing code from your terminal:</p>
      <input
        type="text"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="e.g. aB3x_K9m..."
        style={{ width: '100%', marginBottom: '10px', boxSizing: 'border-box' }}
      />
      <button onClick={handlePair} disabled={loading || !code}>
        {loading ? 'Pairing...' : 'Pair'}
      </button>
      {error && <div style={{ color: 'red', marginTop: '5px' }}>{error}</div>}
    </div>
  );
};

export default PairDialog;
