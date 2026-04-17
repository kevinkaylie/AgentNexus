import{A as e,E as t,P as n,R as r,V as i,c as a,d as o,g as s,h as c,i as l,it as u,l as d,m as f,t as p,u as m,w as h,x as g}from"./_plugin-vue_export-helper-Bfi6r8i4.js";import{J as _,d as v,f as y,lt as b,p as x,t as S,x as C,y as w}from"./client-BCqwyZ4b.js";import{r as T,t as E}from"./inputtext-0Kw9aOBy.js";var D=C.extend({name:`steps`,style:`
    .p-steps {
        position: relative;
    }

    .p-steps-list {
        padding: 0;
        margin: 0;
        list-style-type: none;
        display: flex;
    }

    .p-steps-item {
        position: relative;
        display: flex;
        justify-content: center;
        flex: 1 1 auto;
    }

    .p-steps-item.p-disabled,
    .p-steps-item.p-disabled * {
        opacity: 1;
        pointer-events: auto;
        user-select: auto;
        cursor: auto;
    }

    .p-steps-item:before {
        content: ' ';
        border-top: 2px solid dt('steps.separator.background');
        width: 100%;
        top: 50%;
        left: 0;
        display: block;
        position: absolute;
        margin-top: calc(-1rem + 1px);
    }

    .p-steps-item:first-child::before {
        width: calc(50% + 1rem);
        transform: translateX(100%);
    }

    .p-steps-item:last-child::before {
        width: 50%;
    }

    .p-steps-item-link {
        display: inline-flex;
        flex-direction: column;
        align-items: center;
        overflow: hidden;
        text-decoration: none;
        transition:
            outline-color dt('steps.transition.duration'),
            box-shadow dt('steps.transition.duration');
        border-radius: dt('steps.item.link.border.radius');
        outline-color: transparent;
        gap: dt('steps.item.link.gap');
    }

    .p-steps-item-link:not(.p-disabled):focus-visible {
        box-shadow: dt('steps.item.link.focus.ring.shadow');
        outline: dt('steps.item.link.focus.ring.width') dt('steps.item.link.focus.ring.style') dt('steps.item.link.focus.ring.color');
        outline-offset: dt('steps.item.link.focus.ring.offset');
    }

    .p-steps-item-label {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
        color: dt('steps.item.label.color');
        display: block;
        font-weight: dt('steps.item.label.font.weight');
    }

    .p-steps-item-number {
        display: flex;
        align-items: center;
        justify-content: center;
        color: dt('steps.item.number.color');
        border: 2px solid dt('steps.item.number.border.color');
        background: dt('steps.item.number.background');
        min-width: dt('steps.item.number.size');
        height: dt('steps.item.number.size');
        line-height: dt('steps.item.number.size');
        font-size: dt('steps.item.number.font.size');
        z-index: 1;
        border-radius: dt('steps.item.number.border.radius');
        position: relative;
        font-weight: dt('steps.item.number.font.weight');
    }

    .p-steps-item-number::after {
        content: ' ';
        position: absolute;
        width: 100%;
        height: 100%;
        border-radius: dt('steps.item.number.border.radius');
        box-shadow: dt('steps.item.number.shadow');
    }

    .p-steps:not(.p-readonly) .p-steps-item {
        cursor: pointer;
    }

    .p-steps-item-active .p-steps-item-number {
        background: dt('steps.item.number.active.background');
        border-color: dt('steps.item.number.active.border.color');
        color: dt('steps.item.number.active.color');
    }

    .p-steps-item-active .p-steps-item-label {
        color: dt('steps.item.label.active.color');
    }
`,classes:{root:function(e){return[`p-steps p-component`,{"p-readonly":e.props.readonly}]},list:`p-steps-list`,item:function(e){var t=e.instance,n=e.item,r=e.index;return[`p-steps-item`,{"p-steps-item-active":t.isActive(r),"p-disabled":t.isItemDisabled(n,r)}]},itemLink:`p-steps-item-link`,itemNumber:`p-steps-item-number`,itemLabel:`p-steps-item-label`}}),O={name:`Steps`,extends:{name:`BaseSteps`,extends:w,props:{id:{type:String},model:{type:Array,default:null},readonly:{type:Boolean,default:!0},activeStep:{type:Number,default:0}},style:D,provide:function(){return{$pcSteps:this,$parentInstance:this}}},inheritAttrs:!1,emits:[`update:activeStep`,`step-change`],data:function(){return{d_activeStep:this.activeStep}},watch:{activeStep:function(e){this.d_activeStep=e}},mounted:function(){var e=this.findFirstItem();e&&(e.tabIndex=`0`)},methods:{getPTOptions:function(e,t,n){return this.ptm(e,{context:{item:t,index:n,active:this.isActive(n),disabled:this.isItemDisabled(t,n)}})},onItemClick:function(e,t,n){if(this.disabled(t)||this.readonly){e.preventDefault();return}t.command&&t.command({originalEvent:e,item:t}),n!==this.d_activeStep&&(this.d_activeStep=n,this.$emit(`update:activeStep`,this.d_activeStep)),this.$emit(`step-change`,{originalEvent:e,index:n})},onItemKeydown:function(e,t){switch(e.code){case`ArrowRight`:this.navigateToNextItem(e.target),e.preventDefault();break;case`ArrowLeft`:this.navigateToPrevItem(e.target),e.preventDefault();break;case`Home`:this.navigateToFirstItem(e.target),e.preventDefault();break;case`End`:this.navigateToLastItem(e.target),e.preventDefault();break;case`Tab`:break;case`Enter`:case`NumpadEnter`:case`Space`:this.onItemClick(e,t),e.preventDefault();break}},navigateToNextItem:function(e){var t=this.findNextItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToPrevItem:function(e){var t=this.findPrevItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToFirstItem:function(e){var t=this.findFirstItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToLastItem:function(e){var t=this.findLastItem(e);t&&this.setFocusToMenuitem(e,t)},findNextItem:function(e){var t=e.parentElement.nextElementSibling;return t?t.children[0]:null},findPrevItem:function(e){var t=e.parentElement.previousElementSibling;return t?t.children[0]:null},findFirstItem:function(){var e=b(this.$refs.list,`[data-pc-section="item"]`);return e?e.children[0]:null},findLastItem:function(){var e=_(this.$refs.list,`[data-pc-section="item"]`);return e?e[e.length-1].children[0]:null},setFocusToMenuitem:function(e,t){e.tabIndex=`-1`,t.tabIndex=`0`,t.focus()},isActive:function(e){return e===this.d_activeStep},isItemDisabled:function(e,t){return this.disabled(e)||this.readonly&&!this.isActive(t)},visible:function(e){return typeof e.visible==`function`?e.visible():e.visible!==!1},disabled:function(e){return typeof e.disabled==`function`?e.disabled():e.disabled},label:function(e){return typeof e.label==`function`?e.label():e.label},getMenuItemProps:function(e,t){var n=this;return{action:g({class:this.cx(`itemLink`),onClick:function(t){return n.onItemClick(t,e)},onKeyDown:function(t){return n.onItemKeydown(t,e)}},this.getPTOptions(`itemLink`,e,t)),step:g({class:this.cx(`itemNumber`)},this.getPTOptions(`itemNumber`,e,t)),label:g({class:this.cx(`itemLabel`)},this.getPTOptions(`itemLabel`,e,t))}}}},k=[`id`],A=[`aria-current`,`onClick`,`onKeydown`,`data-p-active`,`data-p-disabled`];function j(n,r,i,s,c,f){return h(),o(`nav`,g({id:n.id,class:n.cx(`root`)},n.ptmi(`root`)),[a(`ol`,g({ref:`list`,class:n.cx(`list`)},n.ptm(`list`)),[(h(!0),o(l,null,t(n.model,function(t,r){return h(),o(l,{key:f.label(t)+`_`+r.toString()},[f.visible(t)?(h(),o(`li`,g({key:0,class:[n.cx(`item`,{item:t,index:r}),t.class],style:t.style,"aria-current":f.isActive(r)?`step`:void 0,onClick:function(e){return f.onItemClick(e,t,r)},onKeydown:function(e){return f.onItemKeydown(e,t,r)}},{ref_for:!0},f.getPTOptions(`item`,t,r),{"data-p-active":f.isActive(r),"data-p-disabled":f.isItemDisabled(t,r)}),[n.$slots.item?(h(),d(e(n.$slots.item),{key:1,item:t,index:r,active:r===c.d_activeStep,label:f.label(t),props:f.getMenuItemProps(t,r)},null,8,[`item`,`index`,`active`,`label`,`props`])):(h(),o(`span`,g({key:0,class:n.cx(`itemLink`)},{ref_for:!0},f.getPTOptions(`itemLink`,t,r)),[a(`span`,g({class:n.cx(`itemNumber`)},{ref_for:!0},f.getPTOptions(`itemNumber`,t,r)),u(r+1),17),a(`span`,g({class:n.cx(`itemLabel`)},{ref_for:!0},f.getPTOptions(`itemLabel`,t,r)),u(f.label(t)),17)],16))],16,A)):m(``,!0)],64)}),128))],16)],16,k)}O.render=j;var M={class:`setup-page`},N={key:0},P={class:`form-field`},F={key:1},I={class:`form-field`},L={key:2},R={class:`method-grid`},z={key:3},B={class:`form-field`},V={key:4},H={class:`command-box`},U={key:0,class:`polling-status`},W={key:1,class:`success-status`},G=p(s({__name:`Setup`,setup(e){let s=r(0),d=[{label:`Set Token`},{label:`Create Owner`},{label:`Choose Method`},{label:`Run Command`},{label:`Verify`}],p=r(``),g=r(``),_=r(`mcp`),b=r(``),C=r(``),w=r(null),D=r(!1),k=r(0),A={mcp:{title:`MCP (Claude Desktop / Cursor)`,description:`适合 AI 编程助手`},sdk:{title:`Python SDK`,description:`适合自定义 Agent`},openclaw:{title:`OpenClaw Skill`,description:`适合已有 OpenClaw Skill`},webhook:{title:`Webhook`,description:`适合任何 HTTP 服务`}},j=[`设置 Daemon Token`,`创建主 DID`,`选择接入方式`,`运行命令`,`等待连接`];function G(){g.value&&(y(g.value),s.value=1)}async function K(){if(p.value)try{let e=await v(p.value);localStorage.setItem(`owner_did`,e.did),s.value=2}catch(e){console.error(`Failed to create owner:`,e)}}function q(e){_.value=e,b.value=``,s.value=3}function J(){let e=b.value;switch(_.value){case`mcp`:return`python main.py node mcp --name "${e}" --caps "Chat,Code"`;case`sdk`:return`import agentnexus\nnexus = await agentnexus.connect("${e}", caps=["Chat", "Code"])`;case`openclaw`:return`curl -X POST http://localhost:8765/adapters/openclaw/register`;case`webhook`:return`curl -X POST http://localhost:8765/adapters/webhook/register`;default:return``}}async function Y(){if(!b.value)return;C.value=J(),D.value=!0,k.value=0,s.value=4;let e=await(await fetch(`/agents/local`)).json(),t=new Set(e.agents.map(e=>e.did)),n=setInterval(async()=>{if(k.value+=2,k.value>=60){clearInterval(n),D.value=!1;return}try{let e=(await(await fetch(`/agents/local`)).json()).agents.find(e=>!t.has(e.did));if(e){clearInterval(n),D.value=!1,w.value=e;let t=localStorage.getItem(`owner_did`);t&&await S(t,e.did)}}catch(e){console.error(`Polling error:`,e)}},2e3)}function X(){navigator.clipboard.writeText(C.value)}function Z(){window.location.href=`/ui/`}return(e,r)=>(h(),o(`div`,M,[r[7]||=a(`h1`,null,`Setup Wizard`,-1),c(i(O),{model:d,activeStep:s.value},null,8,[`activeStep`]),c(i(T),{class:`step-card`},{title:n(()=>[f(u(j[s.value]),1)]),content:n(()=>[s.value===0?(h(),o(`div`,N,[r[4]||=a(`p`,null,`请输入 Daemon Token（从 data/daemon_token.txt 或 ~/.agentnexus/daemon_token.txt 获取）`,-1),a(`div`,P,[r[3]||=a(`label`,null,`Token`,-1),c(i(E),{modelValue:g.value,"onUpdate:modelValue":r[0]||=e=>g.value=e,placeholder:`64字符hex`},null,8,[`modelValue`])]),c(i(x),{label:`确认`,onClick:G,disabled:!g.value},null,8,[`disabled`])])):m(``,!0),s.value===1?(h(),o(`div`,F,[a(`div`,I,[r[5]||=a(`label`,null,`你的名字`,-1),c(i(E),{modelValue:p.value,"onUpdate:modelValue":r[1]||=e=>p.value=e,placeholder:`例如: Kevin`},null,8,[`modelValue`])]),c(i(x),{label:`创建`,onClick:K,disabled:!p.value},null,8,[`disabled`])])):m(``,!0),s.value===2?(h(),o(`div`,L,[a(`div`,R,[(h(),o(l,null,t(A,(e,t)=>c(i(T),{key:t,class:`method-card`,onClick:e=>q(t)},{title:n(()=>[f(u(e.title),1)]),content:n(()=>[a(`p`,null,u(e.description),1)]),_:2},1032,[`onClick`])),64))])])):m(``,!0),s.value===3?(h(),o(`div`,z,[a(`div`,B,[r[6]||=a(`label`,null,`Agent 名称`,-1),c(i(E),{modelValue:b.value,"onUpdate:modelValue":r[2]||=e=>b.value=e,placeholder:`例如: CodeAgent`},null,8,[`modelValue`])]),c(i(x),{label:`生成命令`,onClick:Y,disabled:!b.value},null,8,[`disabled`])])):m(``,!0),s.value===4?(h(),o(`div`,V,[a(`pre`,H,u(C.value),1),c(i(x),{label:`复制`,icon:`pi pi-copy`,text:``,onClick:X}),D.value?(h(),o(`div`,U,[a(`p`,null,`等待中... (已轮询 `+u(k.value)+` 秒)`,1)])):m(``,!0),w.value?(h(),o(`div`,W,[a(`p`,null,`已检测到 Agent: `+u(w.value.profile?.name),1),c(i(x),{label:`完成`,onClick:Z})])):m(``,!0)])):m(``,!0)]),_:1})]))}}),[[`__scopeId`,`data-v-77710038`]]);export{G as default};