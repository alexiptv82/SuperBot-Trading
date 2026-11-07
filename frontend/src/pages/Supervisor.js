import React from 'react';
import { Link } from 'react-router-dom';
import SupervisorTerminal from '../components/SupervisorTerminal';

export default function Supervisor() {
  return <>
    <nav style={{ background:'#0b1323', padding:'12px 16px', color:'#7dd3fc' }}>
      <Link style={{ color:'#7dd3fc' }} to="/overview">Torna ai tre portafogli</Link>
    </nav>
    <SupervisorTerminal />
  </>;
}
