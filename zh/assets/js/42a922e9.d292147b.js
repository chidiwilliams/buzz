"use strict";(self.webpackChunkdocs=self.webpackChunkdocs||[]).push([[143],{3905:(e,n,a)=>{a.d(n,{Zo:()=>u,kt:()=>h});var t=a(7294);function r(e,n,a){return n in e?Object.defineProperty(e,n,{value:a,enumerable:!0,configurable:!0,writable:!0}):e[n]=a,e}function i(e,n){var a=Object.keys(e);if(Object.getOwnPropertySymbols){var t=Object.getOwnPropertySymbols(e);n&&(t=t.filter((function(n){return Object.getOwnPropertyDescriptor(e,n).enumerable}))),a.push.apply(a,t)}return a}function o(e){for(var n=1;n<arguments.length;n++){var a=null!=arguments[n]?arguments[n]:{};n%2?i(Object(a),!0).forEach((function(n){r(e,n,a[n])})):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(a)):i(Object(a)).forEach((function(n){Object.defineProperty(e,n,Object.getOwnPropertyDescriptor(a,n))}))}return e}function l(e,n){if(null==e)return{};var a,t,r=function(e,n){if(null==e)return{};var a,t,r={},i=Object.keys(e);for(t=0;t<i.length;t++)a=i[t],n.indexOf(a)>=0||(r[a]=e[a]);return r}(e,n);if(Object.getOwnPropertySymbols){var i=Object.getOwnPropertySymbols(e);for(t=0;t<i.length;t++)a=i[t],n.indexOf(a)>=0||Object.prototype.propertyIsEnumerable.call(e,a)&&(r[a]=e[a])}return r}var s=t.createContext({}),p=function(e){var n=t.useContext(s),a=n;return e&&(a="function"==typeof e?e(n):o(o({},n),e)),a},u=function(e){var n=p(e.components);return t.createElement(s.Provider,{value:n},e.children)},c="mdxType",d={inlineCode:"code",wrapper:function(e){var n=e.children;return t.createElement(t.Fragment,{},n)}},m=t.forwardRef((function(e,n){var a=e.components,r=e.mdxType,i=e.originalType,s=e.parentName,u=l(e,["components","mdxType","originalType","parentName"]),c=p(a),m=r,h=c["".concat(s,".").concat(m)]||c[m]||d[m]||i;return a?t.createElement(h,o(o({ref:n},u),{},{components:a})):t.createElement(h,o({ref:n},u))}));function h(e,n){var a=arguments,r=n&&n.mdxType;if("string"==typeof e||r){var i=a.length,o=new Array(i);o[0]=m;var l={};for(var s in n)hasOwnProperty.call(n,s)&&(l[s]=n[s]);l.originalType=e,l[c]="string"==typeof e?e:r,o[1]=l;for(var p=2;p<i;p++)o[p]=a[p];return t.createElement.apply(null,o)}return t.createElement.apply(null,a)}m.displayName="MDXCreateElement"},9287:(e,n,a)=>{a.r(n),a.d(n,{assets:()=>s,contentTitle:()=>o,default:()=>d,frontMatter:()=>i,metadata:()=>l,toc:()=>p});var t=a(7462),r=(a(7294),a(3905));const i={title:"\u547d\u4ee4\u884c\u754c\u9762 (CLI)",sidebar_position:5},o=void 0,l={unversionedId:"cli",id:"cli",title:"\u547d\u4ee4\u884c\u754c\u9762 (CLI)",description:"\u547d\u4ee4",source:"@site/i18n/zh/docusaurus-plugin-content-docs/current/cli.md",sourceDirName:".",slug:"/cli",permalink:"/buzz/zh/docs/cli",draft:!1,tags:[],version:"current",sidebarPosition:5,frontMatter:{title:"\u547d\u4ee4\u884c\u754c\u9762 (CLI)",sidebar_position:5},sidebar:"tutorialSidebar",previous:{title:"\u504f\u597d\u8bbe\u7f6e",permalink:"/buzz/zh/docs/preferences"},next:{title:"\u5e38\u89c1\u95ee\u9898\uff08FAQ\uff09",permalink:"/buzz/zh/docs/faq"}},s={},p=[{value:"\u547d\u4ee4",id:"\u547d\u4ee4",level:2},{value:"<code>\u589e\u52a0</code>",id:"\u589e\u52a0",level:3}],u={toc:p},c="wrapper";function d(e){let{components:n,...a}=e;return(0,r.kt)(c,(0,t.Z)({},u,a,{components:n,mdxType:"MDXLayout"}),(0,r.kt)("h2",{id:"\u547d\u4ee4"},"\u547d\u4ee4"),(0,r.kt)("h3",{id:"\u589e\u52a0"},(0,r.kt)("inlineCode",{parentName:"h3"},"\u589e\u52a0")),(0,r.kt)("p",null,"\u542f\u52a8\u4e00\u4e2a\u65b0\u7684\u8f6c\u5f55\u4efb\u52a1\u3002"),(0,r.kt)("pre",null,(0,r.kt)("code",{parentName:"pre"},'Usage: buzz add [options] [file url file...]\n\nOptions:\n  -t, --task <task>              The task to perform. Allowed: translate,\n                                 transcribe. Default: transcribe.\n  -m, --model-type <model-type>  Model type. Allowed: whisper, whispercpp,\n                                 huggingface, fasterwhisper, openaiapi. Default:\n                                 whisper.\n  -s, --model-size <model-size>  Model size. Use only when --model-type is\n                                 whisper, whispercpp, or fasterwhisper. Allowed:\n                                 tiny, base, small, medium, large. Default:\n                                 tiny.\n  --hfid <id>                    Hugging Face model ID. Use only when\n                                 --model-type is huggingface. Example:\n                                 "openai/whisper-tiny"\n  -l, --language <code>          Language code. Allowed: af (Afrikaans), am\n                                 (Amharic), ar (Arabic), as (Assamese), az\n                                 (Azerbaijani), ba (Bashkir), be (Belarusian),\n                                 bg (Bulgarian), bn (Bengali), bo (Tibetan), br\n                                 (Breton), bs (Bosnian), ca (Catalan), cs\n                                 (Czech), cy (Welsh), da (Danish), de (German),\n                                 el (Greek), en (English), es (Spanish), et\n                                 (Estonian), eu (Basque), fa (Persian), fi\n                                 (Finnish), fo (Faroese), fr (French), gl\n                                 (Galician), gu (Gujarati), ha (Hausa), haw\n                                 (Hawaiian), he (Hebrew), hi (Hindi), hr\n                                 (Croatian), ht (Haitian Creole), hu\n                                 (Hungarian), hy (Armenian), id (Indonesian), is\n                                 (Icelandic), it (Italian), ja (Japanese), jw\n                                 (Javanese), ka (Georgian), kk (Kazakh), km\n                                 (Khmer), kn (Kannada), ko (Korean), la (Latin),\n                                 lb (Luxembourgish), ln (Lingala), lo (Lao), lt\n                                 (Lithuanian), lv (Latvian), mg (Malagasy), mi\n                                 (Maori), mk (Macedonian), ml (Malayalam), mn\n                                 (Mongolian), mr (Marathi), ms (Malay), mt\n                                 (Maltese), my (Myanmar), ne (Nepali), nl\n                                 (Dutch), nn (Nynorsk), no (Norwegian), oc\n                                 (Occitan), pa (Punjabi), pl (Polish), ps\n                                 (Pashto), pt (Portuguese), ro (Romanian), ru\n                                 (Russian), sa (Sanskrit), sd (Sindhi), si\n                                 (Sinhala), sk (Slovak), sl (Slovenian), sn\n                                 (Shona), so (Somali), sq (Albanian), sr\n                                 (Serbian), su (Sundanese), sv (Swedish), sw\n                                 (Swahili), ta (Tamil), te (Telugu), tg (Tajik),\n                                 th (Thai), tk (Turkmen), tl (Tagalog), tr\n                                 (Turkish), tt (Tatar), uk (Ukrainian), ur\n                                 (Urdu), uz (Uzbek), vi (Vietnamese), yi\n                                 (Yiddish), yo (Yoruba), zh (Chinese). Leave\n                                 empty to detect language.\n  -p, --prompt <prompt>          Initial prompt.\n  -wt, --word-timestamps         Generate word-level timestamps. (available since 1.2.0)\n  --openai-token <token>         OpenAI access token. Use only when\n                                 --model-type is openaiapi. Defaults to your\n                                 previously saved access token, if one exists.\n  --srt                          Output result in an SRT file.\n  --vtt                          Output result in a VTT file.\n  --txt                          Output result in a TXT file.\n  --hide-gui                     Hide the main application window. (available since 1.2.0)\n  -h, --help                     Displays help on commandline options.\n  --help-all                     Displays help including Qt specific options.\n  -v, --version                  Displays version information.\n\nArguments:\n  files or urls                  Input file paths or urls. Url import availalbe since 1.2.0.\n')),(0,r.kt)("p",null,(0,r.kt)("strong",{parentName:"p"},"\u793a\u4f8b"),":"),(0,r.kt)("pre",null,(0,r.kt)("code",{parentName:"pre",className:"language-shell"},'# \u4f7f\u7528 OpenAI Whisper API \u5c06\u4e24\u4e2a MP3 \u6587\u4ef6\u4ece\u6cd5\u8bed\u7ffb\u8bd1\u4e3a\u82f1\u8bed\nbuzz add --task translate --language fr --model-type openaiapi /Users/user/Downloads/1b3b03e4-8db5-ea2c-ace5-b71ff32e3304.mp3 /Users/user/Downloads/koaf9083k1lkpsfdi0.mp3\n\n# \u4f7f\u7528 Whisper.cpp "small" \u6a21\u578b\u8f6c\u5f55\u4e00\u4e2a MP4 \u6587\u4ef6\uff0c\u5e76\u7acb\u5373\u5bfc\u51fa\u4e3a SRT \u548c VTT \u6587\u4ef6\nbuzz add --task transcribe --model-type whispercpp --model-size small --prompt "My initial prompt\uff08\u6211\u7684\u521d\u59cb\u63d0\u793a\uff09" --srt --vtt /Users/user/Downloads/buzz/1b3b03e4-8db5-ea2c-ace5-b71ff32e3304.mp4\n')))}d.isMDXComponent=!0}}]);