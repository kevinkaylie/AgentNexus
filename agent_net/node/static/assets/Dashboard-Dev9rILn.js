import{C as e,D as t,E as n,P as r,R as i,V as a,c as o,d as s,g as c,h as l,i as u,l as d,m as f,ot as p,t as m,u as h,w as g,x as _}from"./_plugin-vue_export-helper-CQHTXZps.js";import{A as v,O as y,S as b,_ as ee,a as x,g as S,l as C,m as w,p as T,yt as E}from"./client-Il3IMrHd.js";import{i as D}from"./vue-router-BaZL6kbK.js";import{i as O}from"./inputtext-BxEMD2oJ.js";import{n as k,t as A}from"./column-BLMxRXiF.js";import{t as j}from"./tag-wc7Zrxt7.js";var M=v.extend({name:`progressbar`,style:`
    .p-progressbar {
        display: block;
        position: relative;
        overflow: hidden;
        height: dt('progressbar.height');
        background: dt('progressbar.background');
        border-radius: dt('progressbar.border.radius');
    }

    .p-progressbar-value {
        margin: 0;
        background: dt('progressbar.value.background');
    }

    .p-progressbar-label {
        color: dt('progressbar.label.color');
        font-size: dt('progressbar.label.font.size');
        font-weight: dt('progressbar.label.font.weight');
    }

    .p-progressbar-determinate .p-progressbar-value {
        height: 100%;
        width: 0%;
        position: absolute;
        display: none;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        transition: width 1s ease-in-out;
    }

    .p-progressbar-determinate .p-progressbar-label {
        display: inline-flex;
    }

    .p-progressbar-indeterminate .p-progressbar-value::before {
        content: '';
        position: absolute;
        background: inherit;
        inset-block-start: 0;
        inset-inline-start: 0;
        inset-block-end: 0;
        will-change: inset-inline-start, inset-inline-end;
        animation: p-progressbar-indeterminate-anim 2.1s cubic-bezier(0.65, 0.815, 0.735, 0.395) infinite;
    }

    .p-progressbar-indeterminate .p-progressbar-value::after {
        content: '';
        position: absolute;
        background: inherit;
        inset-block-start: 0;
        inset-inline-start: 0;
        inset-block-end: 0;
        will-change: inset-inline-start, inset-inline-end;
        animation: p-progressbar-indeterminate-anim-short 2.1s cubic-bezier(0.165, 0.84, 0.44, 1) infinite;
        animation-delay: 1.15s;
    }

    @keyframes p-progressbar-indeterminate-anim {
        0% {
            inset-inline-start: -35%;
            inset-inline-end: 100%;
        }
        60% {
            inset-inline-start: 100%;
            inset-inline-end: -90%;
        }
        100% {
            inset-inline-start: 100%;
            inset-inline-end: -90%;
        }
    }
    @-webkit-keyframes p-progressbar-indeterminate-anim {
        0% {
            inset-inline-start: -35%;
            inset-inline-end: 100%;
        }
        60% {
            inset-inline-start: 100%;
            inset-inline-end: -90%;
        }
        100% {
            inset-inline-start: 100%;
            inset-inline-end: -90%;
        }
    }

    @keyframes p-progressbar-indeterminate-anim-short {
        0% {
            inset-inline-start: -200%;
            inset-inline-end: 100%;
        }
        60% {
            inset-inline-start: 107%;
            inset-inline-end: -8%;
        }
        100% {
            inset-inline-start: 107%;
            inset-inline-end: -8%;
        }
    }
    @-webkit-keyframes p-progressbar-indeterminate-anim-short {
        0% {
            inset-inline-start: -200%;
            inset-inline-end: 100%;
        }
        60% {
            inset-inline-start: 107%;
            inset-inline-end: -8%;
        }
        100% {
            inset-inline-start: 107%;
            inset-inline-end: -8%;
        }
    }
`,classes:{root:function(e){var t=e.instance;return[`p-progressbar p-component`,{"p-progressbar-determinate":t.determinate,"p-progressbar-indeterminate":t.indeterminate}]},value:`p-progressbar-value`,label:`p-progressbar-label`}}),N={name:`ProgressBar`,extends:{name:`BaseProgressBar`,extends:y,props:{value:{type:Number,default:null},mode:{type:String,default:`determinate`},showValue:{type:Boolean,default:!0}},style:M,provide:function(){return{$pcProgressBar:this,$parentInstance:this}}},inheritAttrs:!1,computed:{progressStyle:function(){return{width:this.value+`%`,display:`flex`}},indeterminate:function(){return this.mode===`indeterminate`},determinate:function(){return this.mode===`determinate`},dataP:function(){return E({determinate:this.determinate,indeterminate:this.indeterminate})}}},P=[`aria-valuenow`,`data-p`],F=[`data-p`],I=[`data-p`],L=[`data-p`];function R(e,n,r,i,a,o){return g(),s(`div`,_({role:`progressbar`,class:e.cx(`root`),"aria-valuemin":`0`,"aria-valuenow":e.value,"aria-valuemax":`100`,"data-p":o.dataP},e.ptmi(`root`)),[o.determinate?(g(),s(`div`,_({key:0,class:e.cx(`value`),style:o.progressStyle,"data-p":o.dataP},e.ptm(`value`)),[e.value!=null&&e.value!==0&&e.showValue?(g(),s(`div`,_({key:0,class:e.cx(`label`),"data-p":o.dataP},e.ptm(`label`)),[t(e.$slots,`default`,{},function(){return[f(p(e.value+`%`),1)]})],16,I)):h(``,!0)],16,F)):o.indeterminate?(g(),s(`div`,_({key:1,class:e.cx(`value`),"data-p":o.dataP},e.ptm(`value`)),null,16,L)):h(``,!0)],16,P)}N.render=R;var z={class:`dashboard`},B={class:`dashboard-header`},V={class:`stats-grid`},H={class:`stat-value`},U={class:`stat-value`},W={class:`stat-value`},G={class:`stat-value`},K={class:`playbook-header`},q={class:`playbook-name`},J=[`onClick`],Y={class:`objective-text`},X={key:0,class:`id-short`},Z={key:1,class:`text-muted`},Q={class:`message-list`},te={class:`msg-from`},ne={class:`msg-content`},re={class:`msg-time`},$=m(c({__name:`Dashboard`,setup(t){let c=D(),m=i([]),_=i([]),v=i([]),y=i([]),E=i([]),M=i(!0),P=i(``),F=i(``);e(async()=>{if(P.value=localStorage.getItem(`owner_did`)||``,F.value=localStorage.getItem(`secretary_did`)||``,!P.value){M.value=!1;return}try{m.value=(await S(P.value,P.value)).agents;try{_.value=(await ee(P.value,P.value)).workers}catch{}try{v.value=((await w(P.value,P.value)).intakes||[]).slice(0,5)}catch{}try{y.value=(await x(P.value,P.value,5)).messages}catch{}let e=await T(P.value),t=[];for(let n of e.enclaves||[])try{let e=await C(n.enclave_id,P.value);e&&e.run_status===`running`&&t.push({enclave_id:n.enclave_id,enclave_name:n.name,run_id:e.run_id,playbook_name:e.playbook_name,current_stage:e.current_stage,status:e.run_status,stages:e.stages})}catch{}E.value=t}catch(e){console.error(`Failed to load dashboard:`,e)}M.value=!1});function I(e){let t=Date.now()/1e3-e;return t<60?`刚刚`:t<3600?`${Math.floor(t/60)} 分钟前`:t<86400?`${Math.floor(t/3600)} 小时前`:new Date(e*1e3).toLocaleDateString()}function L(e){try{let t=JSON.parse(e);return t.summary?t.summary:t.title?t.title:JSON.stringify(t).slice(0,80)}catch{return e.slice(0,80)}}function R(e){if(!e)return 0;let t=Object.values(e);if(t.length===0)return 0;let n=t.filter(e=>e.status===`completed`).length;return Math.round(n/t.length*100)}function $(e){switch(e){case`running`:return`warn`;case`completed`:return`success`;case`blocked`:return`danger`;case`failed`:return`danger`;case`aborted`:return`danger`;default:return`info`}}function ie(e,t){c.push({path:`/enclaves`,query:{enclave_id:e,run_id:t}})}function ae(e){c.push({path:`/enclaves`,query:{intake_session:e}})}function oe(){c.push(`/setup`)}return(e,t)=>(g(),s(`div`,z,[o(`div`,B,[t[0]||=o(`h1`,null,`AgentNexus Dashboard`,-1),P.value?h(``,!0):(g(),d(a(b),{key:0,label:`开始设置`,icon:`pi pi-plus`,onClick:oe}))]),o(`div`,V,[l(a(O),null,{title:r(()=>[...t[1]||=[f(`Agents`,-1)]]),content:r(()=>[o(`span`,H,p(m.value.length),1)]),_:1}),l(a(O),null,{title:r(()=>[...t[2]||=[f(`Workers`,-1)]]),content:r(()=>[o(`span`,U,p(_.value.length),1)]),_:1}),l(a(O),null,{title:r(()=>[...t[3]||=[f(`Active Runs`,-1)]]),content:r(()=>[o(`span`,W,p(E.value.length),1)]),_:1}),l(a(O),null,{title:r(()=>[...t[4]||=[f(`Intakes`,-1)]]),content:r(()=>[o(`span`,G,p(v.value.length),1)]),_:1})]),_.value.length>0?(g(),d(a(O),{key:0,class:`workers-card`},{title:r(()=>[...t[5]||=[f(`Workers`,-1)]]),content:r(()=>[l(a(k),{value:_.value,loading:M.value},{default:r(()=>[l(a(A),{field:`name`,header:`Name`}),l(a(A),{field:`profile_type`,header:`Type`},{body:r(({data:e})=>[l(a(j),{value:e.profile_type,severity:`info`},null,8,[`value`])]),_:1}),l(a(A),{field:`worker_type`,header:`Worker Type`},{body:r(({data:e})=>[l(a(j),{value:e.worker_type||`resident`,severity:`secondary`},null,8,[`value`])]),_:1}),l(a(A),{field:`presence`,header:`Presence`},{body:r(({data:e})=>[l(a(j),{value:e.presence||`offline`,severity:e.presence===`available`?`success`:e.presence===`busy`?`warn`:`danger`},null,8,[`value`,`severity`])]),_:1}),l(a(A),{field:`capabilities`,header:`Capabilities`},{body:r(({data:e})=>[(g(!0),s(u,null,n(e.capabilities||[],e=>(g(),d(a(j),{key:e,value:e,severity:`info`,class:`cap-tag`},null,8,[`value`]))),128))]),_:1})]),_:1},8,[`value`,`loading`])]),_:1})):h(``,!0),E.value.length>0?(g(),d(a(O),{key:1,class:`playbooks-card`},{title:r(()=>[...t[6]||=[f(`Active Playbooks`,-1)]]),content:r(()=>[(g(!0),s(u,null,n(E.value,e=>(g(),s(`div`,{key:e.run_id,class:`playbook-item`},[o(`div`,K,[o(`span`,q,p(e.enclave_name)+` / `+p(e.playbook_name),1),l(a(j),{value:e.current_stage,severity:`warn`},null,8,[`value`]),l(a(b),{label:`查看`,severity:`info`,text:``,size:`small`,onClick:t=>ie(e.enclave_id,e.run_id)},null,8,[`onClick`])]),l(a(N),{value:R(e.stages),"show-value":!0,class:`playbook-progress`},null,8,[`value`])]))),128))]),_:1})):h(``,!0),v.value.length>0?(g(),d(a(O),{key:2,class:`intakes-card`},{title:r(()=>[...t[7]||=[f(`Recent Intakes`,-1)]]),content:r(()=>[l(a(k),{value:v.value,loading:M.value},{default:r(()=>[l(a(A),{field:`session_id`,header:`Session`},{body:r(({data:e})=>[o(`a`,{class:`link`,onClick:t=>ae(e.session_id)},p(e.session_id.slice(0,20))+`...`,9,J)]),_:1}),l(a(A),{field:`objective`,header:`Objective`},{body:r(({data:e})=>[o(`span`,Y,p(e.objective.slice(0,40))+`...`,1)]),_:1}),l(a(A),{field:`status`,header:`Status`},{body:r(({data:e})=>[l(a(j),{value:e.status,severity:$(e.status)},null,8,[`value`,`severity`])]),_:1}),l(a(A),{field:`run_id`,header:`Run`},{body:r(({data:e})=>[e.run_id?(g(),s(`span`,X,p(e.run_id),1)):(g(),s(`span`,Z,`--`))]),_:1})]),_:1},8,[`value`,`loading`])]),_:1})):h(``,!0),y.value.length>0?(g(),d(a(O),{key:3,class:`messages-card`},{title:r(()=>[...t[8]||=[f(`Recent Messages`,-1)]]),content:r(()=>[o(`ul`,Q,[(g(!0),s(u,null,n(y.value,e=>(g(),s(`li`,{key:e.id,class:`message-item`},[o(`span`,te,p(e.from_did.slice(0,20))+`...`,1),o(`span`,ne,p(L(e.content)),1),o(`span`,re,p(I(e.timestamp)),1)]))),128))])]),_:1})):h(``,!0)]))}}),[[`__scopeId`,`data-v-768c16e5`]]);export{$ as default};