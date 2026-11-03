import {describe,it,expect} from 'vitest';
import {applyChatEvent,finishAssistantMessage,updateAssistantMessage} from '@/core/chat/reducer';
import type {ChatThread,AssistantMessage,ChatStep} from '@/core/chat/types';
const assistant=():AssistantMessage=>({id:'a',role:'assistant',reasoning:'',steps:[],text:'',status:'streaming'});
const thread=():ChatThread=>({id:'t',title:'Question',documentIds:['d'],messages:[{id:'u',role:'user',text:'Question',files:[]},assistant()],todos:[],updatedAt:1});
const step:ChatStep={id:'retrieve',kind:'search',label:'Retrieving',status:'active'};
const answer=(t:ChatThread)=>t.messages[1] as AssistantMessage;
describe('Conversation reducer',()=>{
 it('records backend session without replacing browser ID',()=>{const t=applyChatEvent(thread(),'a',{type:'session',serverThreadId:'server'});expect(t.serverThreadId).toBe('server');expect(t.id).toBe('t')});
 it('preserves source selection on session update',()=>expect(applyChatEvent(thread(),'a',{type:'session',serverThreadId:'s'}).documentIds).toEqual(['d']));
 it('updates conversation title',()=>expect(applyChatEvent(thread(),'a',{type:'title',title:'New'}).title).toBe('New'));
 it('replaces to-do state',()=>expect(applyChatEvent(thread(),'a',{type:'todos',todos:[{content:'Find evidence',status:'pending'}]}).todos).toHaveLength(1));
 it('appends answer fragments in order',()=>{let t=applyChatEvent(thread(),'a',{type:'text',delta:'Hello '});t=applyChatEvent(t,'a',{type:'text',delta:'world'});expect(answer(t).text).toBe('Hello world')});
 it('preserves Unicode answer content',()=>expect(answer(applyChatEvent(thread(),'a',{type:'text',delta:'蓝色 💙'})).text).toBe('蓝色 💙'));
 it('appends reasoning independently from answer',()=>{const t=applyChatEvent(thread(),'a',{type:'reasoning',delta:'Evidence'});expect(answer(t).reasoning).toBe('Evidence');expect(answer(t).text).toBe('')});
 it('inserts retrieval step',()=>expect(answer(applyChatEvent(thread(),'a',{type:'step',step})).steps).toEqual([step]));
 it('updates existing step without duplicate',()=>{let t=applyChatEvent(thread(),'a',{type:'step',step});t=applyChatEvent(t,'a',{type:'step',step:{...step,status:'complete'}});expect(answer(t).steps).toEqual([{...step,status:'complete'}])});
 it('preserves distinct step order',()=>{let t=applyChatEvent(thread(),'a',{type:'step',step});t=applyChatEvent(t,'a',{type:'step',step:{...step,id:'answer'}});expect(answer(t).steps.map(s=>s.id)).toEqual(['retrieve','answer'])});
 it('stores citation metadata and warnings',()=>{const citation={citation:1,document_id:'d',document_title:'Manual',edition:'v1',number:'2',kind:'section',page:3};const t=applyChatEvent(thread(),'a',{type:'sources',citations:[citation],warnings:['Fallback']});expect(answer(t).citations).toEqual([citation]);expect(answer(t).warnings).toEqual(['Fallback'])});
 it('clears previous sources on empty evidence',()=>{const t=thread();answer(t).warnings=['Old'];expect(answer(applyChatEvent(t,'a',{type:'sources',citations:[],warnings:[]})).warnings).toEqual([])});
 it('does not mutate input conversation',()=>{const t=thread(),snapshot=structuredClone(t);applyChatEvent(t,'a',{type:'text',delta:'new'});expect(t).toEqual(snapshot)});
 it('does not update user message even with matching ID',()=>expect(updateAssistantMessage(thread(),'u',m=>({...m,text:'bad'})).messages[0].text).toBe('Question'));
 it('leaves messages unchanged for missing target',()=>{const t=thread();expect(updateAssistantMessage(t,'missing',m=>({...m,text:'bad'})).messages).toEqual(t.messages)});
 it('completes answer and records duration',()=>{const a=finishAssistantMessage(assistant(),'complete',3);expect(a.status).toBe('complete');expect(a.durationSeconds).toBe(3)});
 it('stopping preserves partial answer and settles steps',()=>{const a=finishAssistantMessage({...assistant(),text:'partial',steps:[step]},'stopped',2);expect(a.text).toBe('partial');expect(a.status).toBe('stopped');expect(a.steps[0].status).toBe('stopped')});
 it('error preserves explanation and does not mutate input',()=>{const original={...assistant(),error:'Network'};const result=finishAssistantMessage(original,'error',1);expect(result.error).toBe('Network');expect(result.status).toBe('error');expect(original.status).toBe('streaming')});
});
it('replaces provisional tokens with the validated answer without duplication',()=>{
 let t=applyChatEvent(thread(),'a',{type:'text',delta:'Unverified draft'});
 t=applyChatEvent(t,'a',{type:'text-replace',text:'Validated [1]'});
 expect(answer(t).text).toBe('Validated [1]');
});

it('preserves failed stages when finishing a response',()=>{
 const a=finishAssistantMessage({...assistant(),steps:[{...step,status:'failed'}]},'error',1);
 expect(a.steps[0].status).toBe('failed');
});
it('marks unfinished stages failed when the stream errors',()=>{
 const a=finishAssistantMessage({...assistant(),steps:[step]},'error',1);
 expect(a.steps[0].status).toBe('failed');
});
it('successful retry replaces the failed stage without duplicating it',()=>{
 let t=applyChatEvent(thread(),'a',{type:'step',step:{...step,status:'failed'}});
 t=applyChatEvent(t,'a',{type:'step',step:{...step,status:'complete'}});
 expect(answer(t).steps).toEqual([{...step,status:'complete'}]);
});
