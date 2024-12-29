"use strict";(self.webpackChunkdocs=self.webpackChunkdocs||[]).push([[884],{3905:(t,e,n)=>{n.d(e,{Zo:()=>c,kt:()=>m});var r=n(7294);function o(t,e,n){return e in t?Object.defineProperty(t,e,{value:n,enumerable:!0,configurable:!0,writable:!0}):t[e]=n,t}function a(t,e){var n=Object.keys(t);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(t);e&&(r=r.filter((function(e){return Object.getOwnPropertyDescriptor(t,e).enumerable}))),n.push.apply(n,r)}return n}function i(t){for(var e=1;e<arguments.length;e++){var n=null!=arguments[e]?arguments[e]:{};e%2?a(Object(n),!0).forEach((function(e){o(t,e,n[e])})):Object.getOwnPropertyDescriptors?Object.defineProperties(t,Object.getOwnPropertyDescriptors(n)):a(Object(n)).forEach((function(e){Object.defineProperty(t,e,Object.getOwnPropertyDescriptor(n,e))}))}return t}function s(t,e){if(null==t)return{};var n,r,o=function(t,e){if(null==t)return{};var n,r,o={},a=Object.keys(t);for(r=0;r<a.length;r++)n=a[r],e.indexOf(n)>=0||(o[n]=t[n]);return o}(t,e);if(Object.getOwnPropertySymbols){var a=Object.getOwnPropertySymbols(t);for(r=0;r<a.length;r++)n=a[r],e.indexOf(n)>=0||Object.prototype.propertyIsEnumerable.call(t,n)&&(o[n]=t[n])}return o}var l=r.createContext({}),u=function(t){var e=r.useContext(l),n=e;return t&&(n="function"==typeof t?t(e):i(i({},e),t)),n},c=function(t){var e=u(t.components);return r.createElement(l.Provider,{value:e},t.children)},p="mdxType",d={inlineCode:"code",wrapper:function(t){var e=t.children;return r.createElement(r.Fragment,{},e)}},f=r.forwardRef((function(t,e){var n=t.components,o=t.mdxType,a=t.originalType,l=t.parentName,c=s(t,["components","mdxType","originalType","parentName"]),p=u(n),f=o,m=p["".concat(l,".").concat(f)]||p[f]||d[f]||a;return n?r.createElement(m,i(i({ref:e},c),{},{components:n})):r.createElement(m,i({ref:e},c))}));function m(t,e){var n=arguments,o=e&&e.mdxType;if("string"==typeof t||o){var a=n.length,i=new Array(a);i[0]=f;var s={};for(var l in e)hasOwnProperty.call(e,l)&&(s[l]=e[l]);s.originalType=t,s[p]="string"==typeof t?t:o,i[1]=s;for(var u=2;u<a;u++)i[u]=n[u];return r.createElement.apply(null,i)}return r.createElement.apply(null,n)}f.displayName="MDXCreateElement"},9676:(t,e,n)=>{n.r(e),n.d(e,{assets:()=>l,contentTitle:()=>i,default:()=>d,frontMatter:()=>a,metadata:()=>s,toc:()=>u});var r=n(7462),o=(n(7294),n(3905));const a={title:"Translations"},i=void 0,s={unversionedId:"usage/translations",id:"usage/translations",title:"Translations",description:"Default Translation task uses Whisper model ability to translate to English. Since version 1.0.0 Buzz supports additional AI translations to any other language.",source:"@site/docs/usage/3_translations.md",sourceDirName:"usage",slug:"/usage/translations",permalink:"/buzz/docs/usage/translations",draft:!1,tags:[],version:"current",sidebarPosition:3,frontMatter:{title:"Translations"},sidebar:"tutorialSidebar",previous:{title:"Live Recording",permalink:"/buzz/docs/usage/live_recording"},next:{title:"Edit and Resize",permalink:"/buzz/docs/usage/edit_and_resize"}},l={},u=[],c={toc:u},p="wrapper";function d(t){let{components:e,...n}=t;return(0,o.kt)(p,(0,r.Z)({},c,n,{components:e,mdxType:"MDXLayout"}),(0,o.kt)("p",null,"Default ",(0,o.kt)("inlineCode",{parentName:"p"},"Translation")," task uses Whisper model ability to translate to English. Since version ",(0,o.kt)("inlineCode",{parentName:"p"},"1.0.0")," Buzz supports additional AI translations to any other language. "),(0,o.kt)("p",null,"To use translation feature you will need to configure OpenAI API key and translation settings. Set OpenAI API ket in Preferences. Buzz also supports custom locally running translation AIs that support OpenAI API. For more information on locally running AIs see ",(0,o.kt)("a",{parentName:"p",href:"https://ollama.com/blog/openai-compatibility"},"ollama")," or ",(0,o.kt)("a",{parentName:"p",href:"https://lmstudio.ai/"},"LM Studio"),". For information on available custom APIs see this ",(0,o.kt)("a",{parentName:"p",href:"https://github.com/chidiwilliams/buzz/discussions/827"},"discussion thread")),(0,o.kt)("p",null,"To configure translation for Live recordings enable it in Advances settings dialog of the Live Recording settings. Enter AI model to use and prompt with instructions for the AI on how to translate. Translation option is also available for files that already have speech recognised. Use Translate button on transcription viewer toolbar."),(0,o.kt)("p",null,'For AI to know how to translate enter translation instructions in the "Instructions for AI" section. In your instructions you should describe to what language you want it to translate the text to. Also, you may need to add additional instructions to not add any notes or comments as AIs tend to add them. Example instructions to translate English subtitles to Spanish:'),(0,o.kt)("blockquote",null,(0,o.kt)("p",{parentName:"blockquote"},"You are a professional translator, skilled in translating English to Spanish. You will only translate each sentence sent to you into Spanish and not add any notes or comments.")),(0,o.kt)("p",null,'If you enable "Enable live recording transcription export" in Preferences, Live text transcripts will be exported to a text file as they get generated and translated. This file can be used to further integrate Live transcripts with other applications like OBS Studio.'),(0,o.kt)("p",null,"Approximate cost of translation for 1 hour long audio with ChatGPT ",(0,o.kt)("inlineCode",{parentName:"p"},"gpt-4o")," model is around 0.50$"))}d.isMDXComponent=!0}}]);