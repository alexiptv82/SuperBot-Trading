import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { LongShadowStatus } from './LongShadowDashboard';

describe('LONG Shadow UI safety contracts', () => {
  test('missing API is unavailable, not an empty wallet', () => {
    const html = renderToStaticMarkup(<LongShadowStatus data={null} error />);
    expect(html).toContain('non disponibile');
    expect(html).toContain('Nessuna decisione del LONG');
  });

  test('CANDIDATE is explicitly non-executable', () => {
    const data = {
      engine_running: false, enabled: false, can_execute_orders: false,
      consumers: {
        hawk: {
          wallet_status: 'ok',
          positions: { BTCUSDT: {short_open: true,long_open:false} },
          advisory_status: 'unverified_external_record',
          advice: {symbol:'BTCUSDT',setup:'CONTINUATION',
                   decision:'CANDIDATE',reasons:['snapshot_only']},
        },
      },
    };
    const html = renderToStaticMarkup(<LongShadowStatus data={data} />);
    expect(html).toContain('CANDIDATE · NON eseguibile');
    expect(html).toContain('SHORT aperto');
    expect(html).toContain('motore non avviato');
  });

  test('missing wallet is not shown as empty position', () => {
    const data={consumers:{brain:{wallet_status:'unavailable'}}};
    const html=renderToStaticMarkup(<LongShadowStatus data={data}/>);
    expect(html).toContain('Il wallet assente non viene interpretato come vuoto');
    expect(html).not.toContain('nessuna posizione sul simbolo');
  });

  test('NO_TRADE does not imply an executed position', () => {
    const data={consumers:{bull:{
      wallet_status:'unavailable',advisory_status:'unverified_external_record',
      advice:{symbol:'ETHUSDT',setup:'REVERSAL',decision:'NO_TRADE',reasons:['SETUP_ABSENT']}
    }}};
    const html=renderToStaticMarkup(<LongShadowStatus data={data}/>);
    expect(html).toContain('NO_TRADE · nessuna apertura');
    expect(html).toContain('Record esterno, non certificato');
  });
});
