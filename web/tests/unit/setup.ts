import '@testing-library/jest-dom/vitest';
import {afterEach,vi} from 'vitest';
import {cleanup} from '@testing-library/react';
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();if(typeof localStorage!=='undefined')localStorage.clear()});
if(typeof window!=='undefined'){
 Object.defineProperty(window,'matchMedia',{writable:true,value:vi.fn().mockImplementation(query=>({matches:false,media:query,addEventListener:vi.fn(),removeEventListener:vi.fn()}))});
 globalThis.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};
 HTMLElement.prototype.scrollIntoView=vi.fn();
 HTMLElement.prototype.hasPointerCapture=()=>false;
 HTMLElement.prototype.setPointerCapture=()=>{};
 HTMLElement.prototype.releasePointerCapture=()=>{};
}
