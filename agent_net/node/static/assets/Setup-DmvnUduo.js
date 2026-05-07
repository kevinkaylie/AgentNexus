import{A as e,C as t,D as n,E as r,F as i,O as a,P as o,R as s,V as c,c as l,d as u,g as d,h as f,i as p,k as m,l as h,m as g,ot as _,rt as v,t as y,u as b,w as x,x as S}from"./_plugin-vue_export-helper-CQHTXZps.js";import{A as C,C as w,Ft as T,Lt as ee,O as E,S as D,_ as te,b as ne,i as re,n as O,rt as k,v as A,vt as j,x as ie,y as ae,yt as M}from"./client-Il3IMrHd.js";import{i as oe}from"./vue-router-BaZL6kbK.js";import{i as N,r as P,t as F}from"./inputtext-BxEMD2oJ.js";import{t as I}from"./tag-wc7Zrxt7.js";import{t as L}from"./chips-DU2hpSds.js";var R=C.extend({name:`steps`,style:`
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
`,classes:{root:function(e){return[`p-steps p-component`,{"p-readonly":e.props.readonly}]},list:`p-steps-list`,item:function(e){var t=e.instance,n=e.item,r=e.index;return[`p-steps-item`,{"p-steps-item-active":t.isActive(r),"p-disabled":t.isItemDisabled(n,r)}]},itemLink:`p-steps-item-link`,itemNumber:`p-steps-item-number`,itemLabel:`p-steps-item-label`}}),z={name:`Steps`,extends:{name:`BaseSteps`,extends:E,props:{id:{type:String},model:{type:Array,default:null},readonly:{type:Boolean,default:!0},activeStep:{type:Number,default:0}},style:R,provide:function(){return{$pcSteps:this,$parentInstance:this}}},inheritAttrs:!1,emits:[`update:activeStep`,`step-change`],data:function(){return{d_activeStep:this.activeStep}},watch:{activeStep:function(e){this.d_activeStep=e}},mounted:function(){var e=this.findFirstItem();e&&(e.tabIndex=`0`)},methods:{getPTOptions:function(e,t,n){return this.ptm(e,{context:{item:t,index:n,active:this.isActive(n),disabled:this.isItemDisabled(t,n)}})},onItemClick:function(e,t,n){if(this.disabled(t)||this.readonly){e.preventDefault();return}t.command&&t.command({originalEvent:e,item:t}),n!==this.d_activeStep&&(this.d_activeStep=n,this.$emit(`update:activeStep`,this.d_activeStep)),this.$emit(`step-change`,{originalEvent:e,index:n})},onItemKeydown:function(e,t){switch(e.code){case`ArrowRight`:this.navigateToNextItem(e.target),e.preventDefault();break;case`ArrowLeft`:this.navigateToPrevItem(e.target),e.preventDefault();break;case`Home`:this.navigateToFirstItem(e.target),e.preventDefault();break;case`End`:this.navigateToLastItem(e.target),e.preventDefault();break;case`Tab`:break;case`Enter`:case`NumpadEnter`:case`Space`:this.onItemClick(e,t),e.preventDefault();break}},navigateToNextItem:function(e){var t=this.findNextItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToPrevItem:function(e){var t=this.findPrevItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToFirstItem:function(e){var t=this.findFirstItem(e);t&&this.setFocusToMenuitem(e,t)},navigateToLastItem:function(e){var t=this.findLastItem(e);t&&this.setFocusToMenuitem(e,t)},findNextItem:function(e){var t=e.parentElement.nextElementSibling;return t?t.children[0]:null},findPrevItem:function(e){var t=e.parentElement.previousElementSibling;return t?t.children[0]:null},findFirstItem:function(){var e=j(this.$refs.list,`[data-pc-section="item"]`);return e?e.children[0]:null},findLastItem:function(){var e=k(this.$refs.list,`[data-pc-section="item"]`);return e?e[e.length-1].children[0]:null},setFocusToMenuitem:function(e,t){e.tabIndex=`-1`,t.tabIndex=`0`,t.focus()},isActive:function(e){return e===this.d_activeStep},isItemDisabled:function(e,t){return this.disabled(e)||this.readonly&&!this.isActive(t)},visible:function(e){return typeof e.visible==`function`?e.visible():e.visible!==!1},disabled:function(e){return typeof e.disabled==`function`?e.disabled():e.disabled},label:function(e){return typeof e.label==`function`?e.label():e.label},getMenuItemProps:function(e,t){var n=this;return{action:S({class:this.cx(`itemLink`),onClick:function(t){return n.onItemClick(t,e)},onKeyDown:function(t){return n.onItemKeydown(t,e)}},this.getPTOptions(`itemLink`,e,t)),step:S({class:this.cx(`itemNumber`)},this.getPTOptions(`itemNumber`,e,t)),label:S({class:this.cx(`itemLabel`)},this.getPTOptions(`itemLabel`,e,t))}}}},B=[`id`],V=[`aria-current`,`onClick`,`onKeydown`,`data-p-active`,`data-p-disabled`];function H(t,n,i,a,o,s){return x(),u(`nav`,S({id:t.id,class:t.cx(`root`)},t.ptmi(`root`)),[l(`ol`,S({ref:`list`,class:t.cx(`list`)},t.ptm(`list`)),[(x(!0),u(p,null,r(t.model,function(n,r){return x(),u(p,{key:s.label(n)+`_`+r.toString()},[s.visible(n)?(x(),u(`li`,S({key:0,class:[t.cx(`item`,{item:n,index:r}),n.class],style:n.style,"aria-current":s.isActive(r)?`step`:void 0,onClick:function(e){return s.onItemClick(e,n,r)},onKeydown:function(e){return s.onItemKeydown(e,n,r)}},{ref_for:!0},s.getPTOptions(`item`,n,r),{"data-p-active":s.isActive(r),"data-p-disabled":s.isItemDisabled(n,r)}),[t.$slots.item?(x(),h(e(t.$slots.item),{key:1,item:n,index:r,active:r===o.d_activeStep,label:s.label(n),props:s.getMenuItemProps(n,r)},null,8,[`item`,`index`,`active`,`label`,`props`])):(x(),u(`span`,S({key:0,class:t.cx(`itemLink`)},{ref_for:!0},s.getPTOptions(`itemLink`,n,r)),[l(`span`,S({class:t.cx(`itemNumber`)},{ref_for:!0},s.getPTOptions(`itemNumber`,n,r)),_(r+1),17),l(`span`,S({class:t.cx(`itemLabel`)},{ref_for:!0},s.getPTOptions(`itemLabel`,n,r)),_(s.label(n)),17)],16))],16,V)):b(``,!0)],64)}),128))],16)],16,B)}z.render=H;var U=C.extend({name:`message`,style:`
    .p-message {
        display: grid;
        grid-template-rows: 1fr;
        border-radius: dt('message.border.radius');
        outline-width: dt('message.border.width');
        outline-style: solid;
    }

    .p-message-content-wrapper {
        min-height: 0;
    }

    .p-message-content {
        display: flex;
        align-items: center;
        padding: dt('message.content.padding');
        gap: dt('message.content.gap');
    }

    .p-message-icon {
        flex-shrink: 0;
    }

    .p-message-close-button {
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        margin-inline-start: auto;
        overflow: hidden;
        position: relative;
        width: dt('message.close.button.width');
        height: dt('message.close.button.height');
        border-radius: dt('message.close.button.border.radius');
        background: transparent;
        transition:
            background dt('message.transition.duration'),
            color dt('message.transition.duration'),
            outline-color dt('message.transition.duration'),
            box-shadow dt('message.transition.duration'),
            opacity 0.3s;
        outline-color: transparent;
        color: inherit;
        padding: 0;
        border: none;
        cursor: pointer;
        user-select: none;
    }

    .p-message-close-icon {
        font-size: dt('message.close.icon.size');
        width: dt('message.close.icon.size');
        height: dt('message.close.icon.size');
    }

    .p-message-close-button:focus-visible {
        outline-width: dt('message.close.button.focus.ring.width');
        outline-style: dt('message.close.button.focus.ring.style');
        outline-offset: dt('message.close.button.focus.ring.offset');
    }

    .p-message-info {
        background: dt('message.info.background');
        outline-color: dt('message.info.border.color');
        color: dt('message.info.color');
        box-shadow: dt('message.info.shadow');
    }

    .p-message-info .p-message-close-button:focus-visible {
        outline-color: dt('message.info.close.button.focus.ring.color');
        box-shadow: dt('message.info.close.button.focus.ring.shadow');
    }

    .p-message-info .p-message-close-button:hover {
        background: dt('message.info.close.button.hover.background');
    }

    .p-message-info.p-message-outlined {
        color: dt('message.info.outlined.color');
        outline-color: dt('message.info.outlined.border.color');
    }

    .p-message-info.p-message-simple {
        color: dt('message.info.simple.color');
    }

    .p-message-success {
        background: dt('message.success.background');
        outline-color: dt('message.success.border.color');
        color: dt('message.success.color');
        box-shadow: dt('message.success.shadow');
    }

    .p-message-success .p-message-close-button:focus-visible {
        outline-color: dt('message.success.close.button.focus.ring.color');
        box-shadow: dt('message.success.close.button.focus.ring.shadow');
    }

    .p-message-success .p-message-close-button:hover {
        background: dt('message.success.close.button.hover.background');
    }

    .p-message-success.p-message-outlined {
        color: dt('message.success.outlined.color');
        outline-color: dt('message.success.outlined.border.color');
    }

    .p-message-success.p-message-simple {
        color: dt('message.success.simple.color');
    }

    .p-message-warn {
        background: dt('message.warn.background');
        outline-color: dt('message.warn.border.color');
        color: dt('message.warn.color');
        box-shadow: dt('message.warn.shadow');
    }

    .p-message-warn .p-message-close-button:focus-visible {
        outline-color: dt('message.warn.close.button.focus.ring.color');
        box-shadow: dt('message.warn.close.button.focus.ring.shadow');
    }

    .p-message-warn .p-message-close-button:hover {
        background: dt('message.warn.close.button.hover.background');
    }

    .p-message-warn.p-message-outlined {
        color: dt('message.warn.outlined.color');
        outline-color: dt('message.warn.outlined.border.color');
    }

    .p-message-warn.p-message-simple {
        color: dt('message.warn.simple.color');
    }

    .p-message-error {
        background: dt('message.error.background');
        outline-color: dt('message.error.border.color');
        color: dt('message.error.color');
        box-shadow: dt('message.error.shadow');
    }

    .p-message-error .p-message-close-button:focus-visible {
        outline-color: dt('message.error.close.button.focus.ring.color');
        box-shadow: dt('message.error.close.button.focus.ring.shadow');
    }

    .p-message-error .p-message-close-button:hover {
        background: dt('message.error.close.button.hover.background');
    }

    .p-message-error.p-message-outlined {
        color: dt('message.error.outlined.color');
        outline-color: dt('message.error.outlined.border.color');
    }

    .p-message-error.p-message-simple {
        color: dt('message.error.simple.color');
    }

    .p-message-secondary {
        background: dt('message.secondary.background');
        outline-color: dt('message.secondary.border.color');
        color: dt('message.secondary.color');
        box-shadow: dt('message.secondary.shadow');
    }

    .p-message-secondary .p-message-close-button:focus-visible {
        outline-color: dt('message.secondary.close.button.focus.ring.color');
        box-shadow: dt('message.secondary.close.button.focus.ring.shadow');
    }

    .p-message-secondary .p-message-close-button:hover {
        background: dt('message.secondary.close.button.hover.background');
    }

    .p-message-secondary.p-message-outlined {
        color: dt('message.secondary.outlined.color');
        outline-color: dt('message.secondary.outlined.border.color');
    }

    .p-message-secondary.p-message-simple {
        color: dt('message.secondary.simple.color');
    }

    .p-message-contrast {
        background: dt('message.contrast.background');
        outline-color: dt('message.contrast.border.color');
        color: dt('message.contrast.color');
        box-shadow: dt('message.contrast.shadow');
    }

    .p-message-contrast .p-message-close-button:focus-visible {
        outline-color: dt('message.contrast.close.button.focus.ring.color');
        box-shadow: dt('message.contrast.close.button.focus.ring.shadow');
    }

    .p-message-contrast .p-message-close-button:hover {
        background: dt('message.contrast.close.button.hover.background');
    }

    .p-message-contrast.p-message-outlined {
        color: dt('message.contrast.outlined.color');
        outline-color: dt('message.contrast.outlined.border.color');
    }

    .p-message-contrast.p-message-simple {
        color: dt('message.contrast.simple.color');
    }

    .p-message-text {
        font-size: dt('message.text.font.size');
        font-weight: dt('message.text.font.weight');
    }

    .p-message-icon {
        font-size: dt('message.icon.size');
        width: dt('message.icon.size');
        height: dt('message.icon.size');
    }

    .p-message-sm .p-message-content {
        padding: dt('message.content.sm.padding');
    }

    .p-message-sm .p-message-text {
        font-size: dt('message.text.sm.font.size');
    }

    .p-message-sm .p-message-icon {
        font-size: dt('message.icon.sm.size');
        width: dt('message.icon.sm.size');
        height: dt('message.icon.sm.size');
    }

    .p-message-sm .p-message-close-icon {
        font-size: dt('message.close.icon.sm.size');
        width: dt('message.close.icon.sm.size');
        height: dt('message.close.icon.sm.size');
    }

    .p-message-lg .p-message-content {
        padding: dt('message.content.lg.padding');
    }

    .p-message-lg .p-message-text {
        font-size: dt('message.text.lg.font.size');
    }

    .p-message-lg .p-message-icon {
        font-size: dt('message.icon.lg.size');
        width: dt('message.icon.lg.size');
        height: dt('message.icon.lg.size');
    }

    .p-message-lg .p-message-close-icon {
        font-size: dt('message.close.icon.lg.size');
        width: dt('message.close.icon.lg.size');
        height: dt('message.close.icon.lg.size');
    }

    .p-message-outlined {
        background: transparent;
        outline-width: dt('message.outlined.border.width');
    }

    .p-message-simple {
        background: transparent;
        outline-color: transparent;
        box-shadow: none;
    }

    .p-message-simple .p-message-content {
        padding: dt('message.simple.content.padding');
    }

    .p-message-outlined .p-message-close-button:hover,
    .p-message-simple .p-message-close-button:hover {
        background: transparent;
    }

    .p-message-enter-active {
        animation: p-animate-message-enter 0.3s ease-out forwards;
        overflow: hidden;
    }

    .p-message-leave-active {
        animation: p-animate-message-leave 0.15s ease-in forwards;
        overflow: hidden;
    }

    @keyframes p-animate-message-enter {
        from {
            opacity: 0;
            grid-template-rows: 0fr;
        }
        to {
            opacity: 1;
            grid-template-rows: 1fr;
        }
    }

    @keyframes p-animate-message-leave {
        from {
            opacity: 1;
            grid-template-rows: 1fr;
        }
        to {
            opacity: 0;
            margin: 0;
            grid-template-rows: 0fr;
        }
    }
`,classes:{root:function(e){var t=e.props;return[`p-message p-component p-message-`+t.severity,{"p-message-outlined":t.variant===`outlined`,"p-message-simple":t.variant===`simple`,"p-message-sm":t.size===`small`,"p-message-lg":t.size===`large`}]},contentWrapper:`p-message-content-wrapper`,content:`p-message-content`,icon:`p-message-icon`,text:`p-message-text`,closeButton:`p-message-close-button`,closeIcon:`p-message-close-icon`}}),W={name:`BaseMessage`,extends:E,props:{severity:{type:String,default:`info`},closable:{type:Boolean,default:!1},life:{type:Number,default:null},icon:{type:String,default:void 0},closeIcon:{type:String,default:void 0},closeButtonProps:{type:null,default:null},size:{type:String,default:null},variant:{type:String,default:null}},style:U,provide:function(){return{$pcMessage:this,$parentInstance:this}}};function G(e){"@babel/helpers - typeof";return G=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},G(e)}function K(e,t,n){return(t=q(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function q(e){var t=J(e,`string`);return G(t)==`symbol`?t:t+``}function J(e,t){if(G(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(G(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var Y={name:`Message`,extends:W,inheritAttrs:!1,emits:[`close`,`life-end`],timeout:null,data:function(){return{visible:!0}},mounted:function(){var e=this;this.life&&setTimeout(function(){e.visible=!1,e.$emit(`life-end`)},this.life)},methods:{close:function(e){this.visible=!1,this.$emit(`close`,e)}},computed:{closeAriaLabel:function(){return this.$primevue.config.locale.aria?this.$primevue.config.locale.aria.close:void 0},dataP:function(){return M(K(K({outlined:this.variant===`outlined`,simple:this.variant===`simple`},this.severity,this.severity),this.size,this.size))}},directives:{ripple:w},components:{TimesIcon:P}};function X(e){"@babel/helpers - typeof";return X=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},X(e)}function Z(e,t){var n=Object.keys(e);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(e);t&&(r=r.filter(function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable})),n.push.apply(n,r)}return n}function Q(e){for(var t=1;t<arguments.length;t++){var n=arguments[t]==null?{}:arguments[t];t%2?Z(Object(n),!0).forEach(function(t){$(e,t,n[t])}):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(n)):Z(Object(n)).forEach(function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(n,t))})}return e}function $(e,t,n){return(t=se(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function se(e){var t=ce(e,`string`);return X(t)==`symbol`?t:t+``}function ce(e,t){if(X(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(X(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var le=[`data-p`],ue=[`data-p`],de=[`data-p`],fe=[`aria-label`,`data-p`],pe=[`data-p`];function me(t,r,s,c,d,f){var p=a(`TimesIcon`),g=m(`ripple`);return x(),h(T,S({name:`p-message`,appear:``},t.ptmi(`transition`)),{default:o(function(){return[d.visible?(x(),u(`div`,S({key:0,class:t.cx(`root`),role:`alert`,"aria-live":`assertive`,"aria-atomic":`true`,"data-p":f.dataP},t.ptm(`root`)),[l(`div`,S({class:t.cx(`contentWrapper`)},t.ptm(`contentWrapper`)),[t.$slots.container?n(t.$slots,`container`,{key:0,closeCallback:f.close}):(x(),u(`div`,S({key:1,class:t.cx(`content`),"data-p":f.dataP},t.ptm(`content`)),[n(t.$slots,`icon`,{class:v(t.cx(`icon`))},function(){return[(x(),h(e(t.icon?`span`:null),S({class:[t.cx(`icon`),t.icon],"data-p":f.dataP},t.ptm(`icon`)),null,16,[`class`,`data-p`]))]}),t.$slots.default?(x(),u(`div`,S({key:0,class:t.cx(`text`),"data-p":f.dataP},t.ptm(`text`)),[n(t.$slots,`default`)],16,de)):b(``,!0),t.closable?i((x(),u(`button`,S({key:1,class:t.cx(`closeButton`),"aria-label":f.closeAriaLabel,type:`button`,onClick:r[0]||=function(e){return f.close(e)},"data-p":f.dataP},Q(Q({},t.closeButtonProps),t.ptm(`closeButton`))),[n(t.$slots,`closeicon`,{},function(){return[t.closeIcon?(x(),u(`i`,S({key:0,class:[t.cx(`closeIcon`),t.closeIcon],"data-p":f.dataP},t.ptm(`closeIcon`)),null,16,pe)):(x(),h(p,S({key:1,class:[t.cx(`closeIcon`),t.closeIcon],"data-p":f.dataP},t.ptm(`closeIcon`)),null,16,[`class`,`data-p`]))]})],16,fe)),[[g]]):b(``,!0)],16,ue))],16)],16,le)):b(``,!0)]}),_:3},16)}Y.render=me;var he={class:`setup-page`},ge={key:0},_e={class:`form-field`},ve={key:1},ye={class:`form-field`},be={key:2},xe={class:`form-field`},Se={key:3},Ce={class:`form-row`},we={key:0,class:`worker-list`},Te={class:`worker-name`},Ee=[`value`,`onChange`],De={key:1,class:`selected-roles`},Oe={class:`worker-name`},ke={key:4},Ae={class:`form-field`},je={class:`form-field`},Me={class:`form-field`},Ne={key:5},Pe={key:0,class:`result-card`},Fe={class:`result-row`},Ie={class:`value`},Le={class:`result-row`},Re={class:`value`},ze={class:`result-row`},Be={class:`value`},Ve={class:`result-actions`},He=y(d({__name:`Setup`,setup(e){let n=oe(),a=s(0),d=[{label:`设置 Token`},{label:`创建 Owner`},{label:`注册秘书`},{label:`配置 Worker`},{label:`发起 Dispatch`},{label:`完成`}],m=s(``),v=s(``),y=s(``),S=s(``),C=s(`Secretary`),w=s([]),T=s([]),E=s({}),k=s(``),j=s([]),M=s(``),P=s([`developer`]),R=s(``),B=s(null),V=s(``),H=s(!1);t(async()=>{let e=localStorage.getItem(`owner_did`);if(e){y.value=e;let t=localStorage.getItem(`secretary_did`);t?(S.value=t,a.value=3):a.value=2}});function U(){m.value&&(ne(m.value),a.value=1)}async function W(){if(v.value)try{let e=await ae(v.value);y.value=e.did,localStorage.setItem(`owner_did`,e.did),a.value=2}catch(e){console.error(`Failed to create owner:`,e)}}async function G(){if(y.value)try{let e=await A({name:C.value||`Secretary`,type:`secretary`,capabilities:[`orchestrate`,`intake`,`dispatch`],worker_type:`resident`});await O(y.value,e.did),S.value=e.did,localStorage.setItem(`secretary_did`,e.did),a.value=3}catch(e){console.error(`Failed to register secretary:`,e)}}async function K(){if(!(!y.value||!S.value))try{let e=await te(y.value,y.value);w.value=e.workers;for(let t of e.workers)E.value[t.did]=t.name}catch(e){console.error(`Failed to load workers:`,e)}}t(async()=>{a.value>=3&&await K()});async function q(){if(!(!k.value||!y.value))try{let e=await A({name:k.value,capabilities:j.value,worker_type:`resident`});await O(y.value,e.did),T.value.push({did:e.did,role:`developer`}),k.value=``,j.value=[],await K()}catch(e){console.error(`Failed to register worker:`,e)}}async function J(e,t){if(y.value)try{await ie(e,t,y.value)}catch(e){console.error(`Failed to set worker type:`,e)}}async function X(){a.value=4,await K()}async function Z(){if(!(!y.value||!S.value||!M.value)){H.value=!0,V.value=``;try{let e=`sess_${Date.now()}`,t=await re({session_id:e,owner_did:y.value,actor_did:S.value,objective:M.value,required_roles:P.value,preferred_playbook:R.value||void 0,entry_mode:`owner_pre_authorized`,source:{channel:`web`,message_ref:``}});B.value=t,localStorage.setItem(`last_session_id`,e),localStorage.setItem(`last_run_id`,t.run_id),localStorage.setItem(`last_enclave_id`,t.enclave_id),a.value=5}catch(e){V.value=e instanceof Error?e.message:`Dispatch failed`}finally{H.value=!1}}}function Q(){n.push(`/`)}function $(){B.value&&n.push({path:`/enclaves`,query:{enclave_id:B.value.enclave_id,run_id:B.value.run_id}})}return(e,t)=>(x(),u(`div`,he,[t[27]||=l(`h1`,null,`Setup Wizard`,-1),f(c(z),{model:d,activeStep:a.value,class:`setup-steps`},null,8,[`activeStep`]),f(c(N),{class:`step-card`},{title:o(()=>[g(_(d[a.value].label),1)]),content:o(()=>[a.value===0?(x(),u(`div`,ge,[t[9]||=l(`p`,null,`请输入 Daemon Token（从 data/daemon_token.txt 或 ~/.agentnexus/daemon_token.txt 获取）`,-1),l(`div`,_e,[t[8]||=l(`label`,null,`Token`,-1),f(c(F),{modelValue:m.value,"onUpdate:modelValue":t[0]||=e=>m.value=e,placeholder:`64 字符 hex`},null,8,[`modelValue`])]),f(c(D),{label:`确认`,onClick:U,disabled:!m.value},null,8,[`disabled`])])):b(``,!0),a.value===1?(x(),u(`div`,ve,[t[11]||=l(`p`,null,`创建主 DID（Owner），代表你的身份管理所有子 Agent。`,-1),l(`div`,ye,[t[10]||=l(`label`,null,`你的名字`,-1),f(c(F),{modelValue:v.value,"onUpdate:modelValue":t[1]||=e=>v.value=e,placeholder:`例如: Kevin`},null,8,[`modelValue`])]),f(c(D),{label:`创建`,onClick:W,disabled:!v.value},null,8,[`disabled`])])):b(``,!0),a.value===2?(x(),u(`div`,be,[t[13]||=l(`p`,null,`注册常驻秘书 Agent，它将代表你的主 DID 负责任务分派和团队编排。`,-1),l(`div`,xe,[t[12]||=l(`label`,null,`秘书名称`,-1),f(c(F),{modelValue:C.value,"onUpdate:modelValue":t[2]||=e=>C.value=e,placeholder:`例如: Secretary`},null,8,[`modelValue`])]),f(c(D),{label:`注册秘书`,onClick:G,disabled:!C.value},null,8,[`disabled`])])):b(``,!0),a.value===3?(x(),u(`div`,Se,[t[18]||=l(`p`,null,`注册 Worker Agent 并确认 worker_type。至少需要注册一个与 required_roles 匹配的 Worker。`,-1),f(c(N),{class:`register-worker-card`},{title:o(()=>[...t[14]||=[g(`注册新 Worker`,-1)]]),content:o(()=>[l(`div`,Ce,[f(c(F),{modelValue:k.value,"onUpdate:modelValue":t[3]||=e=>k.value=e,placeholder:`Agent 名称`,class:`flex-1`},null,8,[`modelValue`]),f(c(L),{modelValue:j.value,"onUpdate:modelValue":t[4]||=e=>j.value=e,placeholder:`能力标签`,class:`flex-2`},null,8,[`modelValue`]),f(c(D),{label:`注册`,onClick:q,disabled:!k.value},null,8,[`disabled`])])]),_:1}),w.value.length>0?(x(),u(`div`,we,[t[16]||=l(`h3`,null,`已注册 Worker`,-1),(x(!0),u(p,null,r(w.value,e=>(x(),u(`div`,{key:e.did,class:`worker-row`},[l(`span`,Te,_(e.name),1),f(c(I),{value:e.profile_type,severity:`info`},null,8,[`value`]),f(c(I),{value:e.worker_type||`resident`,severity:`secondary`},null,8,[`value`]),f(c(I),{value:e.presence||`offline`,severity:e.presence===`available`?`success`:e.presence===`busy`?`warn`:`danger`},null,8,[`value`,`severity`]),l(`select`,{class:`worker-type-select`,value:e.worker_type||`resident`,onChange:t=>J(e.did,t.target.value)},[...t[15]||=[l(`option`,{value:`resident`},`resident`,-1),l(`option`,{value:`interactive_cli`},`interactive_cli`,-1),l(`option`,{value:`service_worker`},`service_worker`,-1)]],40,Ee)]))),128))])):b(``,!0),T.value.length>0?(x(),u(`div`,De,[t[17]||=l(`h3`,null,`选中的角色`,-1),(x(!0),u(p,null,r(T.value,e=>(x(),u(`div`,{key:e.did,class:`role-row`},[l(`span`,Oe,_(E.value[e.did]||e.did.slice(0,20)),1),f(c(I),{value:e.role,severity:`warn`},null,8,[`value`])]))),128))])):b(``,!0),f(c(D),{label:`完成，发起 Dispatch`,onClick:X,disabled:w.value.length===0},null,8,[`disabled`])])):b(``,!0),a.value===4?(x(),u(`div`,ke,[t[22]||=l(`p`,null,`输入任务目标，秘书将自动选人并启动协作链路。`,-1),l(`div`,Ae,[t[19]||=l(`label`,null,`任务目标`,-1),i(l(`textarea`,{"onUpdate:modelValue":t[5]||=e=>M.value=e,class:`objective-input`,placeholder:`例如: 实现并评审登录模块`,rows:`3`},null,512),[[ee,M.value]])]),l(`div`,je,[t[20]||=l(`label`,null,`所需角色`,-1),f(c(L),{modelValue:P.value,"onUpdate:modelValue":t[6]||=e=>P.value=e},null,8,[`modelValue`])]),l(`div`,Me,[t[21]||=l(`label`,null,`Playbook（可选，留空使用默认）`,-1),f(c(F),{modelValue:R.value,"onUpdate:modelValue":t[7]||=e=>R.value=e,placeholder:`例如: default-orchestration`},null,8,[`modelValue`])]),V.value?(x(),h(c(Y),{key:0,severity:`error`,closable:!1},{default:o(()=>[g(_(V.value),1)]),_:1})):b(``,!0),f(c(D),{label:`发起 Dispatch`,onClick:Z,disabled:!M.value||P.value.length===0,loading:H.value},null,8,[`disabled`,`loading`])])):b(``,!0),a.value===5?(x(),u(`div`,Ne,[f(c(Y),{severity:`success`,closable:!1},{default:o(()=>[...t[23]||=[g(` Dispatch 成功！ `,-1)]]),_:1}),B.value?(x(),u(`div`,Pe,[l(`div`,Fe,[t[24]||=l(`span`,{class:`label`},`Run ID`,-1),l(`span`,Ie,_(B.value.run_id),1)]),l(`div`,Le,[t[25]||=l(`span`,{class:`label`},`Enclave ID`,-1),l(`span`,Re,_(B.value.enclave_id),1)]),l(`div`,ze,[t[26]||=l(`span`,{class:`label`},`Current Stage`,-1),l(`span`,Be,_(B.value.current_stage||`--`),1)])])):b(``,!0),l(`div`,Ve,[f(c(D),{label:`查看 Run 详情`,onClick:$}),f(c(D),{label:`返回 Dashboard`,onClick:Q,text:``})])])):b(``,!0)]),_:1})]))}}),[[`__scopeId`,`data-v-2f2b2019`]]);export{He as default};