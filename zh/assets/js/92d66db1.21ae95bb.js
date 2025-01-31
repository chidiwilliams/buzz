"use strict";(self.webpackChunkdocs=self.webpackChunkdocs||[]).push([[870],{3905:(e,t,n)=>{n.d(t,{Zo:()=>p,kt:()=>m});var r=n(7294);function i(e,t,n){return t in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function o(e,t){var n=Object.keys(e);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(e);t&&(r=r.filter((function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable}))),n.push.apply(n,r)}return n}function a(e){for(var t=1;t<arguments.length;t++){var n=null!=arguments[t]?arguments[t]:{};t%2?o(Object(n),!0).forEach((function(t){i(e,t,n[t])})):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(n)):o(Object(n)).forEach((function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(n,t))}))}return e}function s(e,t){if(null==e)return{};var n,r,i=function(e,t){if(null==e)return{};var n,r,i={},o=Object.keys(e);for(r=0;r<o.length;r++)n=o[r],t.indexOf(n)>=0||(i[n]=e[n]);return i}(e,t);if(Object.getOwnPropertySymbols){var o=Object.getOwnPropertySymbols(e);for(r=0;r<o.length;r++)n=o[r],t.indexOf(n)>=0||Object.prototype.propertyIsEnumerable.call(e,n)&&(i[n]=e[n])}return i}var l=r.createContext({}),c=function(e){var t=r.useContext(l),n=t;return e&&(n="function"==typeof e?e(t):a(a({},t),e)),n},p=function(e){var t=c(e.components);return r.createElement(l.Provider,{value:t},e.children)},u="mdxType",d={inlineCode:"code",wrapper:function(e){var t=e.children;return r.createElement(r.Fragment,{},t)}},f=r.forwardRef((function(e,t){var n=e.components,i=e.mdxType,o=e.originalType,l=e.parentName,p=s(e,["components","mdxType","originalType","parentName"]),u=c(n),f=i,m=u["".concat(l,".").concat(f)]||u[f]||d[f]||o;return n?r.createElement(m,a(a({ref:t},p),{},{components:n})):r.createElement(m,a({ref:t},p))}));function m(e,t){var n=arguments,i=t&&t.mdxType;if("string"==typeof e||i){var o=n.length,a=new Array(o);a[0]=f;var s={};for(var l in t)hasOwnProperty.call(t,l)&&(s[l]=t[l]);s.originalType=e,s[u]="string"==typeof e?e:i,a[1]=s;for(var c=2;c<o;c++)a[c]=n[c];return r.createElement.apply(null,a)}return r.createElement.apply(null,n)}f.displayName="MDXCreateElement"},455:(e,t,n)=>{n.r(t),n.d(t,{assets:()=>l,contentTitle:()=>a,default:()=>d,frontMatter:()=>o,metadata:()=>s,toc:()=>c});var r=n(7462),i=(n(7294),n(3905));const o={title:"Edit and Resize"},a=void 0,s={unversionedId:"usage/edit_and_resize",id:"usage/edit_and_resize",title:"Edit and Resize",description:"When transcript of some audio or video file is generated you can edit it and export to different subtitle formats or plain text. Double-click the transcript in the list of transcripts to see additional options for editing and exporting.",source:"@site/i18n/zh/docusaurus-plugin-content-docs/current/usage/4_edit_and_resize.md",sourceDirName:"usage",slug:"/usage/edit_and_resize",permalink:"/buzz/zh/docs/usage/edit_and_resize",draft:!1,tags:[],version:"current",sidebarPosition:4,frontMatter:{title:"Edit and Resize"},sidebar:"tutorialSidebar",previous:{title:"Translations",permalink:"/buzz/zh/docs/usage/translations"},next:{title:"\u504f\u597d\u8bbe\u7f6e",permalink:"/buzz/zh/docs/preferences"}},l={},c=[],p={toc:c},u="wrapper";function d(e){let{components:t,...n}=e;return(0,i.kt)(u,(0,r.Z)({},p,n,{components:t,mdxType:"MDXLayout"}),(0,i.kt)("p",null,"When transcript of some audio or video file is generated you can edit it and export to different subtitle formats or plain text. Double-click the transcript in the list of transcripts to see additional options for editing and exporting."),(0,i.kt)("p",null,'Transcription view screen has option to resize the transcripts. Click on the "Resize" button so see available options. Transcripts that have been generated ',(0,i.kt)("strong",{parentName:"p"},"with word-level timings")," setting enabled can be combined into subtitles specifying different options, like maximum length of a subtitle and if subtitles should be split on punctuation. For transcripts that have been generated ",(0,i.kt)("strong",{parentName:"p"},"without word-level timings")," setting enabled can only be recombined specifying desired max length of a subtitle.  "),(0,i.kt)("p",null,"If audio file is still present on the system word-level timing merge will also analyze the audio for silences to improve subtitle accuracy. Subtitle generation from transcripts with word-level timings is available since version 1.3.0."))}d.isMDXComponent=!0}}]);