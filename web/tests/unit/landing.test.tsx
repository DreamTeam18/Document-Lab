import {beforeEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import {RagExamples} from '@/components/landing/rag-examples';
const state=vi.hoisted(()=>({active:true,reduced:false}));
vi.mock('@/core/dom/render-activity',()=>({useRenderActivity:()=>state.active,usePrefersReducedMotion:()=>state.reduced}));
vi.mock('next/link',()=>({default:({children,href,...props}:any)=><a href={href} {...props}>{children}</a>}));
// Motion owns animation timing; unit tests assert the component state and content.
vi.mock('motion/react',()=>({AnimatePresence:({children}:any)=>children,motion:{div:({children,initial,animate,exit,transition,...props}:any)=><div {...props}>{children}</div>}}));
beforeEach(()=>{state.active=true;state.reduced=false});
it('labels examples as scripted rather than live answers',()=>{render(<RagExamples/>);expect(screen.getByText(/Scripted illustration using fictional excerpts/)).toBeVisible()});
it('first scenario is selected and associated with its panel',()=>{render(<RagExamples/>);const tab=screen.getByRole('tab',{name:'Find a requirement'});expect(tab).toHaveAttribute('aria-selected','true');expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby',tab.id)});
it('switching scenario changes source and question',()=>{render(<RagExamples/>);fireEvent.click(screen.getByRole('tab',{name:'Connect the details'}));expect(screen.getByText('What should I do before requesting access?')).toBeVisible();expect(screen.getByText('Onboarding guide.pdf')).toBeVisible()});
it('Answer control reveals grounded answer and citation',()=>{render(<RagExamples/>);fireEvent.click(screen.getByRole('button',{name:'Answer',exact:true}));expect(screen.getByText(/Include the document title and edition on every archive label/)).toBeVisible();expect(screen.getByText(/\[1\] Archive manual.pdf/)).toBeVisible()});
it('advances stages on active timer',()=>{vi.useFakeTimers();render(<RagExamples/>);act(()=>vi.advanceTimersByTime(1800));expect(screen.getByText('Planning the search')).toBeVisible()});
it('pause freezes stage progression',()=>{vi.useFakeTimers();render(<RagExamples/>);fireEvent.click(screen.getByRole('button',{name:'Pause preview'}));act(()=>vi.advanceTimersByTime(5400));expect(screen.getByText('Ready to explore')).toBeVisible()});
it('play resumes stage progression',()=>{vi.useFakeTimers();render(<RagExamples/>);fireEvent.click(screen.getByRole('button',{name:'Pause preview'}));fireEvent.click(screen.getByRole('button',{name:'Play preview'}));act(()=>vi.advanceTimersByTime(1800));expect(screen.getByText('Planning the search')).toBeVisible()});
it('offscreen examples do not advance',()=>{state.active=false;vi.useFakeTimers();render(<RagExamples/>);act(()=>vi.advanceTimersByTime(9000));expect(screen.getByText('Ready to explore')).toBeVisible()});
it('reduced motion renders complete answer without waiting',()=>{state.reduced=true;render(<RagExamples/>);expect(screen.getByText(/Include the document title and edition on every archive label/)).toBeVisible()});
it('keyboard navigation moves focus and selection across tabs',()=>{render(<RagExamples/>);const first=screen.getByRole('tab',{name:'Find a requirement'});first.focus();fireEvent.keyDown(first,{key:'ArrowRight'});const second=screen.getByRole('tab',{name:'Connect the details'});expect(second).toHaveFocus();expect(second).toHaveAttribute('aria-selected','true');fireEvent.keyDown(second,{key:'End'});expect(screen.getByRole('tab',{name:'Know what’s missing'})).toHaveFocus()});
