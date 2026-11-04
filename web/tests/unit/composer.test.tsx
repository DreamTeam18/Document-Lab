import {it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Composer} from '@/components/chat/composer';
import {PromptInputProvider} from '@/components/ai-elements/prompt-input';
const toast=vi.hoisted(()=>({info:vi.fn(),error:vi.fn()}));
vi.mock('sonner',()=>({toast}));
function setup(extra:Record<string,unknown>={}){const props={isWelcomeMode:true,isStreaming:false,disabled:false,settings:{mode:'pro' as const,model:'default'},onSettingsChange:vi.fn(),onSubmit:vi.fn(),onStop:vi.fn(),...extra};const result=render(<PromptInputProvider><Composer {...props}/></PromptInputProvider>);return {...result,props,box:screen.getByRole('textbox',{name:'Message'})}}
it('message field has accessible label and character limit',()=>{const {box}=setup();expect(box).toHaveAttribute('maxlength','4000')});
it('source-less composer disables input and send',()=>{const {box}=setup({disabled:true});expect(box).toBeDisabled();expect(screen.getByRole('button',{name:'Send',exact:true})).toBeDisabled()});
it('submits trimmed question',async()=>{const {box,props}=setup();fireEvent.change(box,{target:{value:'  What color?  '}});fireEvent.click(screen.getByRole('button',{name:'Send',exact:true}));await waitFor(()=>expect(props.onSubmit).toHaveBeenCalledWith('What color?',[]))});
it('does not submit whitespace-only question',async()=>{const {box,props}=setup();fireEvent.change(box,{target:{value:'   '}});fireEvent.submit(box.closest('form')!);await new Promise(r=>setTimeout(r,0));expect(props.onSubmit).not.toHaveBeenCalled()});
it('clears draft after successful submission',async()=>{const {box}=setup();fireEvent.change(box,{target:{value:'Question'}});fireEvent.submit(box.closest('form')!);await waitFor(()=>expect(box).toHaveValue(''))});
it('preserves draft when submission throws',async()=>{const {box}=setup({onSubmit:()=>{throw new Error('Select documents')}});fireEvent.change(box,{target:{value:'Question'}});fireEvent.submit(box.closest('form')!);await new Promise(r=>setTimeout(r,0));expect(box).toHaveValue('Question')});
it('stop button aborts rather than submitting another question',()=>{const {props}=setup({isStreaming:true});fireEvent.click(screen.getByRole('button',{name:'Stop',exact:true}));expect(props.onStop).toHaveBeenCalledOnce();expect(props.onSubmit).not.toHaveBeenCalled()});
it('blocks form submission while streaming',async()=>{const {box,props}=setup({isStreaming:true});fireEvent.change(box,{target:{value:'Another'}});fireEvent.submit(box.closest('form')!);await new Promise(r=>setTimeout(r,0));expect(props.onSubmit).not.toHaveBeenCalled()});
it('welcome suggestions populate draft',async()=>{const {box}=setup();fireEvent.click(screen.getByRole('button',{name:'Demo question'}));await waitFor(()=>expect(box).toHaveValue('What must archive labels contain?'))});
it('hides suggestions during established conversation',()=>{setup({isWelcomeMode:false});expect(screen.queryByRole('button',{name:'Demo question'})).not.toBeInTheDocument()});
it('shows evidence disclaimer',()=>{setup();expect(screen.getByText('Answers can make mistakes. Check the cited sources.')).toBeVisible()});
it('renders provided welcome header',()=>{setup({extraHeader:<h2>Choose your sources</h2>});expect(screen.getByRole('heading',{name:'Choose your sources'})).toBeVisible()});
it('file paste directs user to indexed upload',()=>{const {box,props}=setup();fireEvent.paste(box,{clipboardData:{files:[new File(['x'],'x.txt')]}});expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('Upload document'));expect(props.onSubmit).not.toHaveBeenCalled()});
it('file drop directs user to sidebar rather than silently attaching',()=>{const {box}=setup();fireEvent.drop(box,{dataTransfer:{files:[new File(['x'],'x.txt')],types:['Files']}});expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('index files'))});
it('Shift+Enter inserts newline without submitting',async()=>{const {box,props}=setup();await userEvent.type(box,'Line one');await userEvent.keyboard('{Shift>}{Enter}{/Shift}Line two');expect(props.onSubmit).not.toHaveBeenCalled();expect(box).toHaveValue('Line one\nLine two')});

it('explains automatic fallback without a web checkbox or query field',()=>{
 setup({webAvailable:true});
 expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
 expect(screen.queryByRole('textbox',{name:'Public search queries'})).not.toBeInTheDocument();
 expect(screen.getByText(/When documents lack evidence/)).toBeVisible();
});
it('automatic fallback needs only the normal question',async()=>{
 const {box,props}=setup({webAvailable:true});
 fireEvent.change(box,{target:{value:'Compare my documents'}});
 fireEvent.submit(box.closest('form')!);
 await waitFor(()=>expect(props.onSubmit).toHaveBeenCalledWith('Compare my documents',[]));
});
it('unavailable web search leaves document input usable',()=>{
 const {box}=setup({webAvailable:false});
 expect(box).not.toBeDisabled();
 expect(screen.getByText(/Web search is unavailable/)).toBeVisible();
});
