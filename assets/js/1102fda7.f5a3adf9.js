"use strict";(self.webpackChunkdocs=self.webpackChunkdocs||[]).push([[382],{3905:(e,t,n)=>{n.d(t,{Zo:()=>d,kt:()=>f});var a=n(7294);function r(e,t,n){return t in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function l(e,t){var n=Object.keys(e);if(Object.getOwnPropertySymbols){var a=Object.getOwnPropertySymbols(e);t&&(a=a.filter((function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable}))),n.push.apply(n,a)}return n}function i(e){for(var t=1;t<arguments.length;t++){var n=null!=arguments[t]?arguments[t]:{};t%2?l(Object(n),!0).forEach((function(t){r(e,t,n[t])})):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(n)):l(Object(n)).forEach((function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(n,t))}))}return e}function o(e,t){if(null==e)return{};var n,a,r=function(e,t){if(null==e)return{};var n,a,r={},l=Object.keys(e);for(a=0;a<l.length;a++)n=l[a],t.indexOf(n)>=0||(r[n]=e[n]);return r}(e,t);if(Object.getOwnPropertySymbols){var l=Object.getOwnPropertySymbols(e);for(a=0;a<l.length;a++)n=l[a],t.indexOf(n)>=0||Object.prototype.propertyIsEnumerable.call(e,n)&&(r[n]=e[n])}return r}var p=a.createContext({}),s=function(e){var t=a.useContext(p),n=t;return e&&(n="function"==typeof e?e(t):i(i({},t),e)),n},d=function(e){var t=s(e.components);return a.createElement(p.Provider,{value:t},e.children)},c="mdxType",m={inlineCode:"code",wrapper:function(e){var t=e.children;return a.createElement(a.Fragment,{},t)}},u=a.forwardRef((function(e,t){var n=e.components,r=e.mdxType,l=e.originalType,p=e.parentName,d=o(e,["components","mdxType","originalType","parentName"]),c=s(n),u=r,f=c["".concat(p,".").concat(u)]||c[u]||m[u]||l;return n?a.createElement(f,i(i({ref:t},d),{},{components:n})):a.createElement(f,i({ref:t},d))}));function f(e,t){var n=arguments,r=t&&t.mdxType;if("string"==typeof e||r){var l=n.length,i=new Array(l);i[0]=u;var o={};for(var p in t)hasOwnProperty.call(t,p)&&(o[p]=t[p]);o.originalType=e,o[c]="string"==typeof e?e:r,i[1]=o;for(var s=2;s<l;s++)i[s]=n[s];return a.createElement.apply(null,i)}return a.createElement.apply(null,n)}u.displayName="MDXCreateElement"},7137:(e,t,n)=>{n.r(t),n.d(t,{assets:()=>p,contentTitle:()=>i,default:()=>m,frontMatter:()=>l,metadata:()=>o,toc:()=>s});var a=n(7462),r=(n(7294),n(3905));const l={title:"Preferences",sidebar_position:4},i=void 0,o={unversionedId:"preferences",id:"preferences",title:"Preferences",description:"Open the Preferences window from the Menu bar, or click Ctrl/Cmd + ,.",source:"@site/docs/preferences.md",sourceDirName:".",slug:"/preferences",permalink:"/buzz/docs/preferences",draft:!1,tags:[],version:"current",sidebarPosition:4,frontMatter:{title:"Preferences",sidebar_position:4},sidebar:"tutorialSidebar",previous:{title:"Edit and Resize",permalink:"/buzz/docs/usage/edit_and_resize"},next:{title:"CLI",permalink:"/buzz/docs/cli"}},p={},s=[{value:"General Preferences",id:"general-preferences",level:2},{value:"OpenAI API preferences",id:"openai-api-preferences",level:3},{value:"Default export file name",id:"default-export-file-name",level:3},{value:"Live transcript exports",id:"live-transcript-exports",level:3},{value:"Live transcription mode",id:"live-transcription-mode",level:3},{value:"Advanced Preferences",id:"advanced-preferences",level:2},{value:"Available variables",id:"available-variables",level:3}],d={toc:s},c="wrapper";function m(e){let{components:t,...n}=e;return(0,r.kt)(c,(0,a.Z)({},d,n,{components:t,mdxType:"MDXLayout"}),(0,r.kt)("p",null,"Open the Preferences window from the Menu bar, or click ",(0,r.kt)("inlineCode",{parentName:"p"},"Ctrl/Cmd + ,"),"."),(0,r.kt)("h2",{id:"general-preferences"},"General Preferences"),(0,r.kt)("h3",{id:"openai-api-preferences"},"OpenAI API preferences"),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"API Key")," - key to authenticate your requests to OpenAI API. To get API key from OpenAI see ",(0,r.kt)("a",{parentName:"p",href:"https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key"},"this article"),". "),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"Base Url")," - By default all requests are sent to API provided by OpenAI company. Their api url is ",(0,r.kt)("inlineCode",{parentName:"p"},"https://api.openai.com/v1/"),". Compatible APIs are also provided by other companies. List of available API urls you can find on ",(0,r.kt)("a",{parentName:"p",href:"https://github.com/chidiwilliams/buzz/discussions/827"},"discussion page")),(0,r.kt)("h3",{id:"default-export-file-name"},"Default export file name"),(0,r.kt)("p",null,"Sets the default export file name for file transcriptions. For\nexample, a value of ",(0,r.kt)("inlineCode",{parentName:"p"},"{{ input_file_name }} ({{ task }}d on {{ date_time }})")," will save TXT exports\nas ",(0,r.kt)("inlineCode",{parentName:"p"},"Input Filename (transcribed on 19-Sep-2023 20-39-25).txt")," by default."),(0,r.kt)("p",null,"Available variables:"),(0,r.kt)("table",null,(0,r.kt)("thead",{parentName:"table"},(0,r.kt)("tr",{parentName:"thead"},(0,r.kt)("th",{parentName:"tr",align:null},"Key"),(0,r.kt)("th",{parentName:"tr",align:null},"Description"),(0,r.kt)("th",{parentName:"tr",align:null},"Example"))),(0,r.kt)("tbody",{parentName:"table"},(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"input_file_name")),(0,r.kt)("td",{parentName:"tr",align:null},"File name of the imported file"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"audio")," (e.g. if the imported file path was ",(0,r.kt)("inlineCode",{parentName:"td"},"/path/to/audio.wav"))),(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"task")),(0,r.kt)("td",{parentName:"tr",align:null},"Transcription task"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"transcribe"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"translate"))),(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"language")),(0,r.kt)("td",{parentName:"tr",align:null},"Language code"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"en"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"fr"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"yo"),", etc.")),(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"model_type")),(0,r.kt)("td",{parentName:"tr",align:null},"Model type"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"Whisper"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"Whisper.cpp"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"Faster Whisper"),", etc.")),(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"model_size")),(0,r.kt)("td",{parentName:"tr",align:null},"Model size"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"tiny"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"base"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"small"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"medium"),", ",(0,r.kt)("inlineCode",{parentName:"td"},"large"),", etc.")),(0,r.kt)("tr",{parentName:"tbody"},(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"date_time")),(0,r.kt)("td",{parentName:"tr",align:null},"Export time (format: ",(0,r.kt)("inlineCode",{parentName:"td"},"%d-%b-%Y %H-%M-%S"),")"),(0,r.kt)("td",{parentName:"tr",align:null},(0,r.kt)("inlineCode",{parentName:"td"},"19-Sep-2023 20-39-25"))))),(0,r.kt)("h3",{id:"live-transcript-exports"},"Live transcript exports"),(0,r.kt)("p",null,"Live transcription export can be used to integrate Buzz with other applications like OBS Studio.\nWhen enabled, live text transcripts will be exported to a text file as they get generated and translated."),(0,r.kt)("p",null,"If AI translation is enabled for live recordings, the translated text will also be exported to the text file.\nFilename for the translated text will end with ",(0,r.kt)("inlineCode",{parentName:"p"},".translated.txt"),". "),(0,r.kt)("h3",{id:"live-transcription-mode"},"Live transcription mode"),(0,r.kt)("p",null,"Three transcription modes are available:"),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"Append below")," - New sentences will be added below existing with an empty space between them.\nLast sentence will be at the bottom."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"Append above")," - New sentences will be added above existing with an empty space between them.\nLast sentence will be at the top."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"Append and correct")," - New sentences will be added at the end of existing transcript without extra spaces between.\nThis mode will also try to correct errors at the end of previously transcribed sentences. This mode requires more\nprocessing power and more powerful hardware to work."),(0,r.kt)("h2",{id:"advanced-preferences"},"Advanced Preferences"),(0,r.kt)("p",null,"To keep preferences section simple for new users, some more advanced preferences are settable via OS environment variables. Set the necessary environment variables in your OS before starting Buzz or create a script to set them."),(0,r.kt)("p",null,"On MacOS and Linux crete ",(0,r.kt)("inlineCode",{parentName:"p"},"run_buzz.sh")," with the following content:"),(0,r.kt)("pre",null,(0,r.kt)("code",{parentName:"pre",className:"language-bash"},"#!/bin/bash\nexport VARIABLE=value\nexport SOME_OTHER_VARIABLE=some_other_value\nbuzz\n")),(0,r.kt)("p",null,"On Windows crete ",(0,r.kt)("inlineCode",{parentName:"p"},"run_buzz.bat")," with the following content:"),(0,r.kt)("pre",null,(0,r.kt)("code",{parentName:"pre",className:"language-bat"},'@echo off\nset VARIABLE=value\nset SOME_OTHER_VARIABLE=some_other_value\n"C:\\Program Files (x86)\\Buzz\\Buzz.exe"\n')),(0,r.kt)("h3",{id:"available-variables"},"Available variables"),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_WHISPERCPP_N_THREADS")," - Number of threads to use for Whisper.cpp model. Default is ",(0,r.kt)("inlineCode",{parentName:"p"},"4"),". "),(0,r.kt)("p",null,"On a laptop with 16 threads setting ",(0,r.kt)("inlineCode",{parentName:"p"},"BUZZ_WHISPERCPP_N_THREADS=8")," leads to some 15% speedup in transcription time.\nIncreasing number of threads even more will lead in slower transcription time as results from parallel threads has to be\ncombined to produce the final answer."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_TRANSLATION_API_BASE_URl")," - Base URL of OpenAI compatible API to use for translation."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_TRANSLATION_API_KEY")," - Api key of OpenAI compatible API to use for translation."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_MODEL_ROOT")," - Root directory to store model files.\nDefaults to ",(0,r.kt)("a",{parentName:"p",href:"https://pypi.org/project/platformdirs/"},"user_cache_dir"),"."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_FAVORITE_LANGUAGES")," - Coma separated list of supported language codes to show on top of language list."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_LOCALE")," - Buzz UI locale to use. Defaults to one of supported system locales."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_DOWNLOAD_COOKIEFILE")," - Location of a ",(0,r.kt)("a",{parentName:"p",href:"https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"},"cookiefile")," to use for downloading private videos or as workaround for anti-bot protection."),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"BUZZ_FORCE_CPU")," - Will force Buzz to use CPU and not GPU, useful for setups with older GPU if that is slower than GPU or GPU has issues. Example usage ",(0,r.kt)("inlineCode",{parentName:"p"},"BUZZ_FORCE_CPU=true"),". Available since ",(0,r.kt)("inlineCode",{parentName:"p"},"1.2.1")))}m.isMDXComponent=!0}}]);