import React from 'react';
import BrainOperatorReviews from '../components/BrainOperatorReviews';

export default function ClassicalManualReviews(){
  return <main style={{padding:18,paddingBottom:100}}>
    <h2>Memoria delle chiusure · PAPER</h2>
    <p>Falco e Toro conservano soltanto gli esempi che confermi. Le regole meccaniche non cambiano automaticamente.</p>
    <BrainOperatorReviews basePath="/api/desk/operator/hawk" owner="Falco" accountScoped/>
    <BrainOperatorReviews basePath="/api/desk/operator/bull" owner="Toro" accountScoped/>
  </main>;
}
