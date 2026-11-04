// @vitest-environment node
import {it,expect,vi,afterEach} from 'vitest';
import {parseSSE,chatAdapter} from '@/core/chat/adapter';
import type {ChatRequest} from '@/core/chat/types';
const frame=(event:string,data:unknown)=>`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const stream=(text:string,bytes=false)=>new ReadableStream<Uint8Array>({start(c){const data=new TextEncoder().encode(text);if(bytes)for(const b of data)c.enqueue(Uint8Array.of(b));else c.enqueue(data);c.close()}});
const collect=async<T>(iter:AsyncIterable<T>)=>{const out:T[]=[];for await(const x of iter)out.push(x);return out};
const request=():ChatRequest=>({threadId:'local',documentIds:['doc'],messages:[{id:'u',role:'user',text:'Question',files:[]}],files:[],settings:{mode:'pro',model:'default'}});
const run=(r=request())=>collect(chatAdapter.stream(r,new AbortController().signal));
const mock=(text=frame('result',{answer:'Answer'}))=>vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(stream(text))));
afterEach(()=>vi.unstubAllGlobals());
it('parses LF frames',async()=>expect(await collect(parseSSE(stream(frame('result',{answer:'x'}))))).toEqual([{event:'result',data:{answer:'x'}}]));
it('parses byte-fragmented CRLF and Unicode',async()=>expect((await collect(parseSSE(stream(frame('result',{answer:'💙蓝'}).replaceAll('\n','\r\n'),true))))[0].data.answer).toBe('💙蓝'));
it('parses multiple events in one read',async()=>expect(await collect(parseSSE(stream(frame('session',{})+frame('result',{}))))).toHaveLength(2));
it('ignores comment keepalives',async()=>expect(await collect(parseSSE(stream(': ping\n\n'+frame('result',{}))))).toHaveLength(1));
it('defaults absent event name to message',async()=>expect((await collect(parseSSE(stream('data: {}\n\n'))))[0].event).toBe('message'));
it('joins multiline data',async()=>expect((await collect(parseSSE(stream('event: result\ndata: {"answer":\ndata: "yes"}\n\n'))))[0].data.answer).toBe('yes'));
it('rejects malformed JSON',async()=>await expect(collect(parseSSE(stream('data: {bad}\n\n')))).rejects.toThrow());
it('releases reader lock after parsing failure',async()=>{const s=stream('data: bad\n\n');await collect(parseSSE(s)).catch(()=>{});expect(s.locked).toBe(false)});
it('rejects requests with no message before fetch',async()=>{mock();await expect(run({...request(),messages:[]})).rejects.toThrow('Enter a question');expect(fetch).not.toHaveBeenCalled()});
it('rejects requests ending with assistant',async()=>{mock();await expect(run({...request(),messages:[{id:'a',role:'assistant',text:'x',steps:[],reasoning:'',status:'complete'}]})).rejects.toThrow('Enter a question')});
it('sends only latest question and selected IDs',async()=>{mock();const r=request();r.messages.unshift({id:'old',role:'user',text:'Old',files:[]});await run(r);expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual({user_query:'Question',document_ids:['doc'],thread_id:null})});
it('uses backend session ID for follow-up',async()=>{mock();await run({...request(),serverThreadId:'backend'});expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).thread_id).toBe('backend')});
it('maps session event',async()=>{mock(frame('session',{thread_id:'s'})+frame('result',{answer:'x'}));expect((await run())[0]).toEqual({type:'session',serverThreadId:'s'})});
it('maps retrieval progress',async()=>{mock(frame('progress',{step:'retrieve'})+frame('result',{answer:'x'}));expect((await run())[0]).toMatchObject({type:'step',step:{label:'Evidence retrieved',status:'complete'}})});
it('retains unknown progress label',async()=>{mock(frame('progress',{step:'future'})+frame('result',{answer:'x'}));expect((await run())[0]).toMatchObject({step:{label:'future'}})});
it('maps final answer and source metadata',async()=>{mock(frame('result',{answer:'Blue',citations:[{citation:1,page:3}],warnings:['fallback']}));expect(await run()).toEqual([{type:'text',delta:'Blue'},{type:'sources',citations:[{citation:1,page:3}],warnings:['fallback']}])});
it('defaults omitted citations and warnings to empty',async()=>{mock();expect((await run())[1]).toEqual({type:'sources',citations:[],warnings:[]})});
it('propagates useful HTTP error details',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Changed sources'}),{status:409})));await expect(run()).rejects.toThrow('Changed sources')});
it('handles non-JSON HTTP error safely',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>Oops</html>',{status:502})));await expect(run()).rejects.toThrow('Request failed (502)')});
it('propagates SSE errors',async()=>{mock(frame('error',{message:'Provider unavailable'}));await expect(run()).rejects.toThrow('Provider unavailable')});
it('rejects truncated stream without final result',async()=>{mock(frame('session',{thread_id:'s'}));await expect(run()).rejects.toThrow('connection ended')});
it('passes caller cancellation to fetch',async()=>{const controller=new AbortController();controller.abort();vi.stubGlobal('fetch',vi.fn(async(_url,options)=>{(options!.signal as AbortSignal).throwIfAborted();return new Response()}));await expect(collect(chatAdapter.stream(request(),controller.signal))).rejects.toThrow();expect(vi.mocked(fetch).mock.calls[0][1]!.signal!.aborted).toBe(true)});
it('emits tokens before the result and replaces the draft at completion',async()=>{
 let controller!:ReadableStreamDefaultController<Uint8Array>;
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(new ReadableStream<Uint8Array>({start(c){controller=c}}))));
 const iterator=chatAdapter.stream(request(),new AbortController().signal);
 controller?.enqueue(new TextEncoder().encode(frame('token',{delta:'Draft'})));
 expect(await iterator.next()).toEqual({done:false,value:{type:'text',delta:'Draft'}});
 controller.enqueue(new TextEncoder().encode(frame('result',{answer:'Validated [1]',citations:[]})));controller.close();
 expect(await iterator.next()).toEqual({done:false,value:{type:'text-replace',text:'Validated [1]'}});
 await collect(iterator);
});
it('reports a truncated stream after displaying partial tokens',async()=>{
 mock(frame('token',{delta:'Partial'}));
 const iterator=chatAdapter.stream(request(),new AbortController().signal);
 expect((await iterator.next()).value).toEqual({type:'text',delta:'Partial'});
 await expect(iterator.next()).rejects.toThrow('before an answer');
});

it.each([['triage','Request routed'],['conversational','Response prepared'],['hyde','Retrieval hints prepared']])('labels %s progress without exposing classifier details',async(step,label)=>{mock(frame('progress',{step,status:'completed'})+frame('result',{answer:'Hello',citations:[]}));const events=await run();expect(events[0]).toMatchObject({type:'step',step:{id:step,label}});expect(events).toContainEqual({type:'text',delta:'Hello'});});

it('retains backend failure status instead of showing success',async()=>{
 mock(frame('progress',{step:'assess',status:'failed'})+frame('result',{answer:'Insufficient evidence'}));
 expect((await run())[0]).toMatchObject({step:{id:'assess',status:'failed',label:'Evidence checked'}});
});
it('labels recovery and preserves reassessment progress',async()=>{
 mock(frame('progress',{step:'error_handler',status:'completed'})+frame('progress',{step:'assess',status:'completed'})+frame('result',{answer:'Supported [1]'}));
 const events=await run();
 expect(events[0]).toMatchObject({step:{label:'Recovery handled'}});
 expect(events[1]).toMatchObject({step:{id:'assess',status:'complete'}});
});
it('keeps global synthesis citations and partial evidence warnings with final replacement',async()=>{
 const citations=[{citation:2,document_id:'d2',document_title:'Second manual',edition:'v2',number:'3',kind:'section',page:8}];
 mock(frame('token',{delta:'Unverified [99]'})+frame('result',{answer:'Supported [2]',citations,warnings:['Evidence partial for q2.'],usage:{chat_calls:5},plan_size:2}));
 const events=await run();
 expect(events).toContainEqual({type:'text-replace',text:'Supported [2]'});
 expect(events).toContainEqual({type:'sources',citations,warnings:['Evidence partial for q2.']});
});

it('accepts automatic fallback persistence without client web flags',async()=>{
 mock(frame('result',{answer:'Both sections',persisted_answer:'Document section only',persisted_citations:[]}));
 const events=await run(request());
 expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).not.toHaveProperty('web_requested');
 expect(events).toContainEqual({type:'persistence',text:'Document section only',citations:[]});
});
it('maps web progress without treating it as answer text',async()=>{
 mock(frame('progress',{step:'web',status:'completed'})+frame('result',{answer:'Answer'}));
 expect((await run())[0]).toMatchObject({type:'step',step:{label:'Web search and evidence assessment completed'}});
});
