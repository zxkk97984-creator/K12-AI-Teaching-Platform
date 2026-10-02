import {afterEach,describe,expect,it,vi} from 'vitest';
import {saveInteractive} from './api';
vi.mock('../identity/api',async importOriginal=>({...await importOriginal<object>(),ensureCsrfToken:async()=> 'synthetic-csrf'}));
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
describe('checkpoint network deadline',()=>{
  it('exposes a timed-out write as retryable instead of waiting forever',async()=>{
    vi.useFakeTimers();
    const fetch=vi.fn((_path:string, init:RequestInit)=>new Promise((_resolve,reject)=>{
      init.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
    }));
    vi.stubGlobal('fetch',fetch);
    const body={base_revision:2,event_id:'same-lost-event',game_state:{value:4}};
    const first=saveInteractive('session',body);
    const rejected=expect(first).rejects.toThrow('当前操作已保留');
    await vi.advanceTimersByTimeAsync(12000);await rejected;
    expect((fetch.mock.calls[0][1].signal as AbortSignal).aborted).toBe(true);
    fetch.mockImplementationOnce(async()=>new Response(JSON.stringify({id:'session',base_revision:3}),{status:200}));
    expect((await saveInteractive('session',body)).base_revision).toBe(3);
    expect(fetch.mock.calls[0][1].body).toEqual(fetch.mock.calls[1][1].body);
  });
});
