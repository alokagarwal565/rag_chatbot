import React from 'react';
import { ConfidenceLevel } from '../types/api';

interface Props {
  confidence: ConfidenceLevel;
}

export const ConfidenceBadge: React.FC<Props> = ({ confidence }) => {
  const styles: Record<ConfidenceLevel, { bg: string; text: string; border: string; label: string }> = {
    HIGH: { bg: 'rgba(16, 185, 129, 0.15)', text: '#34d399', border: 'rgba(16, 185, 129, 0.4)', label: 'HIGH CONFIDENCE' },
    MEDIUM: { bg: 'rgba(245, 158, 11, 0.15)', text: '#fbbf24', border: 'rgba(245, 158, 11, 0.4)', label: 'MEDIUM CONFIDENCE' },
    LOW: { bg: 'rgba(239, 68, 68, 0.15)', text: '#f87171', border: 'rgba(239, 68, 68, 0.4)', label: 'LOW CONFIDENCE' },
    ABSTAIN: { bg: 'rgba(100, 116, 139, 0.15)', text: '#94a3b8', border: 'rgba(100, 116, 139, 0.4)', label: 'ABSTAINED (NO EVIDENCE)' },
  };

  const style = styles[confidence] || styles.LOW;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.4rem',
        padding: '0.2rem 0.6rem',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 600,
        letterSpacing: '0.05em',
        backgroundColor: style.bg,
        color: style.text,
        border: `1px solid ${style.border}`,
        fontFamily: 'var(--font-mono)'
      }}
    >
      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: style.text }} />
      {style.label}
    </span>
  );
};
