import{C as e,D as t,E as n,F as r,P as i,R as a,V as o,c as s,d as c,g as l,h as u,i as d,l as f,m as p,ot as m,s as h,t as g,u as _,w as v,x as y}from"./_plugin-vue_export-helper-CQHTXZps.js";import{A as b,Lt as ee,O as x,S,c as te,d as ne,f as re,l as ie,p as C,s as ae,t as oe,yt as w}from"./client-Il3IMrHd.js?v=20260626";import{r as se}from"./vue-router-BaZL6kbK.js";import{i as T}from"./inputtext-BxEMD2oJ.js";import{n as E,t as D}from"./column-BLMxRXiF.js";import{t as O}from"./tag-wc7Zrxt7.js";var k=b.extend({name:`divider`,style:`
    .p-divider-horizontal {
        display: flex;
        width: 100%;
        position: relative;
        align-items: center;
        margin: dt('divider.horizontal.margin');
        padding: dt('divider.horizontal.padding');
    }

    .p-divider-horizontal:before {
        position: absolute;
        display: block;
        inset-block-start: 50%;
        inset-inline-start: 0;
        width: 100%;
        content: '';
        border-block-start: 1px solid dt('divider.border.color');
    }

    .p-divider-horizontal .p-divider-content {
        padding: dt('divider.horizontal.content.padding');
    }

    .p-divider-vertical {
        min-height: 100%;
        display: flex;
        position: relative;
        justify-content: center;
        margin: dt('divider.vertical.margin');
        padding: dt('divider.vertical.padding');
    }

    .p-divider-vertical:before {
        position: absolute;
        display: block;
        inset-block-start: 0;
        inset-inline-start: 50%;
        height: 100%;
        content: '';
        border-inline-start: 1px solid dt('divider.border.color');
    }

    .p-divider.p-divider-vertical .p-divider-content {
        padding: dt('divider.vertical.content.padding');
    }

    .p-divider-content {
        z-index: 1;
        background: dt('divider.content.background');
        color: dt('divider.content.color');
    }

    .p-divider-solid.p-divider-horizontal:before {
        border-block-start-style: solid;
    }

    .p-divider-solid.p-divider-vertical:before {
        border-inline-start-style: solid;
    }

    .p-divider-dashed.p-divider-horizontal:before {
        border-block-start-style: dashed;
    }

    .p-divider-dashed.p-divider-vertical:before {
        border-inline-start-style: dashed;
    }

    .p-divider-dotted.p-divider-horizontal:before {
        border-block-start-style: dotted;
    }

    .p-divider-dotted.p-divider-vertical:before {
        border-inline-start-style: dotted;
    }

    .p-divider-left:dir(rtl),
    .p-divider-right:dir(rtl) {
        flex-direction: row-reverse;
    }
`,classes:{root:function(e){var t=e.props;return[`p-divider p-component`,`p-divider-`+t.layout,`p-divider-`+t.type,{"p-divider-left":t.layout===`horizontal`&&(!t.align||t.align===`left`)},{"p-divider-center":t.layout===`horizontal`&&t.align===`center`},{"p-divider-right":t.layout===`horizontal`&&t.align===`right`},{"p-divider-top":t.layout===`vertical`&&t.align===`top`},{"p-divider-center":t.layout===`vertical`&&(!t.align||t.align===`center`)},{"p-divider-bottom":t.layout===`vertical`&&t.align===`bottom`}]},content:`p-divider-content`},inlineStyles:{root:function(e){var t=e.props;return{justifyContent:t.layout===`horizontal`?t.align===`center`||t.align===null?`center`:t.align===`left`?`flex-start`:t.align===`right`?`flex-end`:null:null,alignItems:t.layout===`vertical`?t.align===`center`||t.align===null?`center`:t.align===`top`?`flex-start`:t.align===`bottom`?`flex-end`:null:null}}}}),A={name:`BaseDivider`,extends:x,props:{align:{type:String,default:null},layout:{type:String,default:`horizontal`},type:{type:String,default:`solid`}},style:k,provide:function(){return{$pcDivider:this,$parentInstance:this}}};function j(e){"@babel/helpers - typeof";return j=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},j(e)}function M(e,t,n){return(t=N(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function N(e){var t=P(e,`string`);return j(t)==`symbol`?t:t+``}function P(e,t){if(j(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(j(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var F={name:`Divider`,extends:A,inheritAttrs:!1,computed:{dataP:function(){return w(M(M(M({},this.align,this.align),this.layout,this.layout),this.type,this.type))}}},I=[`aria-orientation`,`data-p`],L=[`data-p`];function R(e,n,r,i,a,o){return v(),c(`div`,y({class:e.cx(`root`),style:e.sx(`root`),role:`separator`,"aria-orientation":e.layout,"data-p":o.dataP},e.ptmi(`root`)),[e.$slots.default?(v(),c(`div`,y({key:0,class:e.cx(`content`),"data-p":o.dataP},e.ptm(`content`)),[t(e.$slots,`default`)],16,L)):_(``,!0)],16,I)}F.render=R;var z={class:`enclaves-page`},B={key:0},V=[`onClick`],H={class:`id-short`},U={key:1,class:`enclave-detail`},W={class:`breadcrumb`},G={class:`info-grid`},K={class:`info-row`},ce={class:`value id-short`},le={class:`info-row`},ue={class:`value`},de={class:`info-grid`},fe={class:`info-row`},pe={class:`value id-short`},me={class:`info-row`},he={class:`value`},ge={class:`info-row`},_e={class:`value`},ve={key:0,class:`info-row`},ye={class:`value`},be={key:0,class:`abort-section`},xe={class:`info-grid`},Se={class:`info-row`},Ce={class:`value id-short`},we={class:`info-row`},Te={class:`value`},Ee={class:`info-row`},De={class:`value`},Oe={class:`info-row`},ke={class:`value`},Ae={class:`info-row`},je={class:`value`},Me={class:`id-short`},Ne={class:`id-short`},q={class:`id-short`},Pe={class:`budget-json`},Fe={class:`vault-value`},J=g(l({__name:`Enclaves`,setup(t){let l=se(),g=a([]),y=a(!0),b=a(null),x=a(null),w=a(null),k=a({}),A=a(``),j=a(!1),M=a(``);e(async()=>{M.value=localStorage.getItem(`owner_did`)||l.query.actor_did||``,M.value&&localStorage.setItem(`owner_did`,M.value),await N();let e=l.query.enclave_id,t=l.query.run_id,n=l.query.intake_session;n&&await L(n),e&&await P(e,t||``)});async function N(){y.value=!0;try{g.value=(await C(M.value)).enclaves}catch(e){console.error(`Failed to load enclaves:`,e)}y.value=!1}async function P(e,t){try{if(b.value=await ae(e,M.value),t)await I(e,t);else try{let t=await ie(e,M.value);t&&await I(e,t.run_id)}catch{x.value=null}}catch(e){console.error(`Failed to load enclave detail:`,e)}}async function I(e,t){try{if(x.value=await ne(e,t,M.value),x.value?.context){let e=x.value.context.context_budget;e&&(k.value._budget=JSON.stringify(e,null,2))}if(x.value?.stages){for(let[,t]of Object.entries(x.value.stages))if(t.output_ref)try{let n=J(t.output_ref);if(n&&n.key){let t=await re(e,n.key,M.value);k.value[n.key]=t.value}}catch{}}}catch(e){console.error(`Failed to load run detail:`,e)}}async function L(e){let t=localStorage.getItem(`secretary_did`)||``;if(t)try{w.value=(await te(e,t)).intake}catch{}}async function R(){if(!(!w.value?.session_id||!M.value)){j.value=!0;try{await oe(w.value.session_id,M.value,A.value||`Aborted by owner via Dashboard`),w.value.session_id&&await L(w.value.session_id)}catch(e){console.error(`Failed to abort:`,e)}finally{j.value=!1}}}function J(e){try{return JSON.parse(e)}catch{return null}}function Ie(e){switch(e){case`completed`:return`success`;case`active`:return`warn`;case`rejected`:return`danger`;case`blocked`:return`danger`;case`timeout`:return`danger`;case`failed`:return`danger`;default:return`info`}}function Y(e){switch(e){case`running`:return`warn`;case`completed`:return`success`;case`failed`:return`danger`;case`aborted`:return`danger`;default:return`info`}}function X(e){return e?new Date(e*1e3).toLocaleString():`--`}let Z=h(()=>x.value?Object.entries(x.value.stages).map(([e,t])=>({stage_name:e,role:t.role,assigned_did:t.assigned_did,status:t.status,retry_count:t.retry_count,task_id:t.task_id,output_ref:t.output_ref,started_at:t.started_at,completed_at:t.completed_at})):[]),Q=h(()=>x.value?.context?x.value.context.context_budget:null);function Le(){b.value=null,x.value=null,w.value=null,k.value={}}function $(e){b.value=e,P(e.enclave_id,``)}return(e,t)=>(v(),c(`div`,z,[t[18]||=s(`h1`,null,`Enclaves & Runs`,-1),b.value?(v(),c(`div`,U,[s(`div`,W,[s(`a`,{class:`link`,onClick:t[0]||=e=>{Le(),N()}},`Enclaves`),t[2]||=s(`span`,null,`/`,-1),s(`span`,null,m(b.value.name),1)]),u(o(T),{class:`enclave-info-card`},{title:i(()=>[p(`Enclave: `+m(b.value.name),1)]),content:i(()=>[s(`div`,G,[s(`div`,K,[t[3]||=s(`span`,{class:`label`},`ID`,-1),s(`span`,ce,m(b.value.enclave_id),1)]),s(`div`,le,[t[4]||=s(`span`,{class:`label`},`Members`,-1),s(`span`,ue,[(v(!0),c(d,null,n(b.value.members,e=>(v(),f(o(O),{key:e.did,value:e.role,severity:`info`,class:`member-tag`},null,8,[`value`]))),128))])])])]),_:1}),w.value?(v(),f(o(T),{key:0,class:`intake-card`},{title:i(()=>[...t[5]||=[p(`Intake`,-1)]]),content:i(()=>[s(`div`,de,[s(`div`,fe,[t[6]||=s(`span`,{class:`label`},`Session`,-1),s(`span`,pe,m(w.value.session_id),1)]),s(`div`,me,[t[7]||=s(`span`,{class:`label`},`Status`,-1),s(`span`,he,[u(o(O),{value:w.value.status,severity:Y(w.value.status)},null,8,[`value`,`severity`])])]),s(`div`,ge,[t[8]||=s(`span`,{class:`label`},`Objective`,-1),s(`span`,_e,m(w.value.objective),1)]),w.value.selected_workers?(v(),c(`div`,ve,[t[9]||=s(`span`,{class:`label`},`Selected Workers`,-1),s(`span`,ye,[(v(!0),c(d,null,n(w.value.selected_workers,(e,t)=>(v(),c(`span`,{key:t,class:`worker-role`},m(t)+`: `+m(e.slice(0,25))+`... `,1))),128))])])):_(``,!0)]),u(o(F)),w.value.status===`running`?(v(),c(`div`,be,[r(s(`input`,{"onUpdate:modelValue":t[1]||=e=>A.value=e,class:`abort-input`,placeholder:`Abort reason (optional)`},null,512),[[ee,A.value]]),u(o(S),{label:`Abort Run`,severity:`danger`,size:`small`,onClick:R,loading:j.value},null,8,[`loading`])])):_(``,!0)]),_:1})):_(``,!0),x.value?(v(),f(o(T),{key:1,class:`run-card`},{title:i(()=>[p(`Run: `+m(x.value.playbook_name),1)]),content:i(()=>[s(`div`,xe,[s(`div`,Se,[t[10]||=s(`span`,{class:`label`},`Run ID`,-1),s(`span`,Ce,m(x.value.run_id),1)]),s(`div`,we,[t[11]||=s(`span`,{class:`label`},`Status`,-1),s(`span`,Te,[u(o(O),{value:x.value.run_status,severity:Y(x.value.run_status)},null,8,[`value`,`severity`])])]),s(`div`,Ee,[t[12]||=s(`span`,{class:`label`},`Current Stage`,-1),s(`span`,De,m(x.value.current_stage),1)]),s(`div`,Oe,[t[13]||=s(`span`,{class:`label`},`Started`,-1),s(`span`,ke,m(X(x.value.started_at)),1)]),s(`div`,Ae,[t[14]||=s(`span`,{class:`label`},`Completed`,-1),s(`span`,je,m(X(x.value.completed_at)),1)])])]),_:1})):_(``,!0),x.value&&Z.value.length>0?(v(),f(o(T),{key:2,class:`stages-card`},{title:i(()=>[...t[15]||=[p(`Stages`,-1)]]),content:i(()=>[u(o(E),{value:Z.value},{default:i(()=>[u(o(D),{field:`stage_name`,header:`Stage`}),u(o(D),{field:`role`,header:`Role`}),u(o(D),{field:`status`,header:`Status`},{body:i(({data:e})=>[u(o(O),{value:e.status,severity:Ie(e.status)},null,8,[`value`,`severity`])]),_:1}),u(o(D),{field:`assigned_did`,header:`Assigned To`},{body:i(({data:e})=>[s(`span`,Me,m(e.assigned_did?.slice(0,25)||`--`),1)]),_:1}),u(o(D),{field:`retry_count`,header:`Retries`}),u(o(D),{field:`task_id`,header:`Task ID`},{body:i(({data:e})=>[s(`span`,Ne,m(e.task_id||`--`),1)]),_:1}),u(o(D),{field:`output_ref`,header:`Output Ref`},{body:i(({data:e})=>[s(`span`,q,m(e.output_ref?.slice(0,30)||`--`),1)]),_:1})]),_:1},8,[`value`])]),_:1})):_(``,!0),Q.value?(v(),f(o(T),{key:3,class:`budget-card`},{title:i(()=>[...t[16]||=[p(`Context Budget`,-1)]]),content:i(()=>[s(`pre`,Pe,m(JSON.stringify(Q.value,null,2)),1)]),_:1})):_(``,!0),Object.keys(k.value).length>0?(v(),f(o(T),{key:4,class:`vault-card`},{title:i(()=>[...t[17]||=[p(`Vault / Manifest Content`,-1)]]),content:i(()=>[(v(!0),c(d,null,n(k.value,(e,t)=>(v(),c(`div`,{key:t,class:`vault-entry`},[s(`h4`,null,m(t),1),s(`pre`,Fe,m(e),1)]))),128))]),_:1})):_(``,!0)])):(v(),c(`div`,B,[u(o(T),null,{content:i(()=>[u(o(E),{value:g.value,loading:y.value},{default:i(()=>[u(o(D),{field:`name`,header:`Name`},{body:i(({data:e})=>[s(`a`,{class:`link`,onClick:t=>$(e)},m(e.name),9,V)]),_:1}),u(o(D),{field:`enclave_id`,header:`ID`},{body:i(({data:e})=>[s(`span`,H,m(e.enclave_id),1)]),_:1}),u(o(D),{field:`members`,header:`Members`},{body:i(({data:e})=>[s(`span`,null,m(e.members?.length||0),1)]),_:1}),u(o(D),{header:`Actions`},{body:i(({data:e})=>[u(o(S),{label:`查看`,severity:`info`,text:``,size:`small`,onClick:t=>$(e)},null,8,[`onClick`])]),_:1})]),_:1},8,[`value`,`loading`])]),_:1})]))]))}}),[[`__scopeId`,`data-v-5b952304`]]);export{J as default};