import{A as e,D as t,E as n,O as r,P as i,c as a,d as o,h as s,i as c,l,ot as u,rt as d,u as f,w as p,x as m}from"./_plugin-vue_export-helper-CQHTXZps.js";import{A as h,D as g,O as _,yt as v}from"./client-Il3IMrHd.js";var y={name:`TimesCircleIcon`,extends:g};function b(e){return w(e)||C(e)||S(e)||x()}function x(){throw TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`)}function S(e,t){if(e){if(typeof e==`string`)return T(e,t);var n={}.toString.call(e).slice(8,-1);return n===`Object`&&e.constructor&&(n=e.constructor.name),n===`Map`||n===`Set`?Array.from(e):n===`Arguments`||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)?T(e,t):void 0}}function C(e){if(typeof Symbol<`u`&&e[Symbol.iterator]!=null||e[`@@iterator`]!=null)return Array.from(e)}function w(e){if(Array.isArray(e))return T(e)}function T(e,t){(t==null||t>e.length)&&(t=e.length);for(var n=0,r=Array(t);n<t;n++)r[n]=e[n];return r}function E(e,t,n,r,i,s){return p(),o(`svg`,m({width:`14`,height:`14`,viewBox:`0 0 14 14`,fill:`none`,xmlns:`http://www.w3.org/2000/svg`},e.pti()),b(t[0]||=[a(`path`,{"fill-rule":`evenodd`,"clip-rule":`evenodd`,d:`M7 14C5.61553 14 4.26215 13.5895 3.11101 12.8203C1.95987 12.0511 1.06266 10.9579 0.532846 9.67879C0.00303296 8.3997 -0.13559 6.99224 0.134506 5.63437C0.404603 4.2765 1.07129 3.02922 2.05026 2.05026C3.02922 1.07129 4.2765 0.404603 5.63437 0.134506C6.99224 -0.13559 8.3997 0.00303296 9.67879 0.532846C10.9579 1.06266 12.0511 1.95987 12.8203 3.11101C13.5895 4.26215 14 5.61553 14 7C14 8.85652 13.2625 10.637 11.9497 11.9497C10.637 13.2625 8.85652 14 7 14ZM7 1.16667C5.84628 1.16667 4.71846 1.50879 3.75918 2.14976C2.79989 2.79074 2.05222 3.70178 1.61071 4.76768C1.16919 5.83358 1.05367 7.00647 1.27876 8.13803C1.50384 9.26958 2.05941 10.309 2.87521 11.1248C3.69102 11.9406 4.73042 12.4962 5.86198 12.7212C6.99353 12.9463 8.16642 12.8308 9.23232 12.3893C10.2982 11.9478 11.2093 11.2001 11.8502 10.2408C12.4912 9.28154 12.8333 8.15373 12.8333 7C12.8333 5.45291 12.2188 3.96918 11.1248 2.87521C10.0308 1.78125 8.5471 1.16667 7 1.16667ZM4.66662 9.91668C4.58998 9.91704 4.51404 9.90209 4.44325 9.87271C4.37246 9.84333 4.30826 9.8001 4.2544 9.74557C4.14516 9.6362 4.0838 9.48793 4.0838 9.33335C4.0838 9.17876 4.14516 9.0305 4.2544 8.92113L6.17553 7L4.25443 5.07891C4.15139 4.96832 4.09529 4.82207 4.09796 4.67094C4.10063 4.51982 4.16185 4.37563 4.26872 4.26876C4.3756 4.16188 4.51979 4.10066 4.67091 4.09799C4.82204 4.09532 4.96829 4.15142 5.07887 4.25446L6.99997 6.17556L8.92106 4.25446C9.03164 4.15142 9.1779 4.09532 9.32903 4.09799C9.48015 4.10066 9.62434 4.16188 9.73121 4.26876C9.83809 4.37563 9.89931 4.51982 9.90198 4.67094C9.90464 4.82207 9.84855 4.96832 9.74551 5.07891L7.82441 7L9.74554 8.92113C9.85478 9.0305 9.91614 9.17876 9.91614 9.33335C9.91614 9.48793 9.85478 9.6362 9.74554 9.74557C9.69168 9.8001 9.62748 9.84333 9.55669 9.87271C9.4859 9.90209 9.40996 9.91704 9.33332 9.91668C9.25668 9.91704 9.18073 9.90209 9.10995 9.87271C9.03916 9.84333 8.97495 9.8001 8.9211 9.74557L6.99997 7.82444L5.07884 9.74557C5.02499 9.8001 4.96078 9.84333 4.88999 9.87271C4.81921 9.90209 4.74326 9.91704 4.66662 9.91668Z`,fill:`currentColor`},null,-1)]),16)}y.render=E;var D=h.extend({name:`chip`,style:`
    .p-chip {
        display: inline-flex;
        align-items: center;
        background: dt('chip.background');
        color: dt('chip.color');
        border-radius: dt('chip.border.radius');
        padding-block: dt('chip.padding.y');
        padding-inline: dt('chip.padding.x');
        gap: dt('chip.gap');
    }

    .p-chip-icon {
        color: dt('chip.icon.color');
        font-size: dt('chip.icon.size');
        width: dt('chip.icon.size');
        height: dt('chip.icon.size');
    }

    .p-chip-image {
        border-radius: 50%;
        width: dt('chip.image.width');
        height: dt('chip.image.height');
        margin-inline-start: calc(-1 * dt('chip.padding.y'));
    }

    .p-chip:has(.p-chip-remove-icon) {
        padding-inline-end: dt('chip.padding.y');
    }

    .p-chip:has(.p-chip-image) {
        padding-block-start: calc(dt('chip.padding.y') / 2);
        padding-block-end: calc(dt('chip.padding.y') / 2);
    }

    .p-chip-remove-icon {
        cursor: pointer;
        font-size: dt('chip.remove.icon.size');
        width: dt('chip.remove.icon.size');
        height: dt('chip.remove.icon.size');
        color: dt('chip.remove.icon.color');
        border-radius: 50%;
        transition:
            outline-color dt('chip.transition.duration'),
            box-shadow dt('chip.transition.duration');
        outline-color: transparent;
    }

    .p-chip-remove-icon:focus-visible {
        box-shadow: dt('chip.remove.icon.focus.ring.shadow');
        outline: dt('chip.remove.icon.focus.ring.width') dt('chip.remove.icon.focus.ring.style') dt('chip.remove.icon.focus.ring.color');
        outline-offset: dt('chip.remove.icon.focus.ring.offset');
    }
`,classes:{root:`p-chip p-component`,image:`p-chip-image`,icon:`p-chip-icon`,label:`p-chip-label`,removeIcon:`p-chip-remove-icon`}}),O={name:`Chip`,extends:{name:`BaseChip`,extends:_,props:{label:{type:[String,Number],default:null},icon:{type:String,default:null},image:{type:String,default:null},removable:{type:Boolean,default:!1},removeIcon:{type:String,default:void 0}},style:D,provide:function(){return{$pcChip:this,$parentInstance:this}}},inheritAttrs:!1,emits:[`remove`],data:function(){return{visible:!0}},methods:{onKeydown:function(e){(e.key===`Enter`||e.key===`Backspace`)&&this.close(e)},close:function(e){this.visible=!1,this.$emit(`remove`,e)}},computed:{dataP:function(){return v({removable:this.removable})}},components:{TimesCircleIcon:y}},k=[`aria-label`,`data-p`],A=[`src`];function j(n,r,i,a,s,c){return s.visible?(p(),o(`div`,m({key:0,class:n.cx(`root`),"aria-label":n.label},n.ptmi(`root`),{"data-p":c.dataP}),[t(n.$slots,`default`,{},function(){return[n.image?(p(),o(`img`,m({key:0,src:n.image},n.ptm(`image`),{class:n.cx(`image`)}),null,16,A)):n.$slots.icon?(p(),l(e(n.$slots.icon),m({key:1,class:n.cx(`icon`)},n.ptm(`icon`)),null,16,[`class`])):n.icon?(p(),o(`span`,m({key:2,class:[n.cx(`icon`),n.icon]},n.ptm(`icon`)),null,16)):f(``,!0),n.label===null?f(``,!0):(p(),o(`div`,m({key:3,class:n.cx(`label`)},n.ptm(`label`)),u(n.label),17))]}),n.removable?t(n.$slots,`removeicon`,{key:0,removeCallback:c.close,keydownCallback:c.onKeydown},function(){return[(p(),l(e(n.removeIcon?`span`:`TimesCircleIcon`),m({class:[n.cx(`removeIcon`),n.removeIcon],onClick:c.close,onKeydown:c.onKeydown},n.ptm(`removeIcon`)),null,16,[`class`,`onClick`,`onKeydown`]))]}):f(``,!0)],16,k)):f(``,!0)}O.render=j;var M=h.extend({name:`inputchips`,style:`
    .p-inputchips {
        display: inline-flex;
    }

    .p-inputchips-input {
        margin: 0;
        list-style-type: none;
        cursor: text;
        overflow: hidden;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        padding: calc(dt('inputchips.padding.y') / 2) dt('inputchips.padding.x');
        gap: calc(dt('inputchips.padding.y') / 2);
        color: dt('inputchips.color');
        background: dt('inputchips.background');
        border: 1px solid dt('inputchips.border.color');
        border-radius: dt('inputchips.border.radius');
        width: 100%;
        transition:
            background dt('inputchips.transition.duration'),
            color dt('inputchips.transition.duration'),
            border-color dt('inputchips.transition.duration'),
            outline-color dt('inputchips.transition.duration'),
            box-shadow dt('inputchips.transition.duration');
        outline-color: transparent;
        box-shadow: dt('inputchips.shadow');
    }

    .p-inputchips:not(.p-disabled):hover .p-inputchips-input {
        border-color: dt('inputchips.hover.border.color');
    }

    .p-inputchips:not(.p-disabled).p-focus .p-inputchips-input {
        border-color: dt('inputchips.focus.border.color');
        box-shadow: dt('inputchips.focus.ring.shadow');
        outline: dt('inputchips.focus.ring.width') dt('inputchips.focus.ring.style') dt('inputchips.focus.ring.color');
        outline-offset: dt('inputchips.focus.ring.offset');
    }

    .p-inputchips.p-invalid .p-inputchips-input {
        border-color: dt('inputchips.invalid.border.color');
    }

    .p-variant-filled.p-inputchips-input {
        background: dt('inputchips.filled.background');
    }

    .p-inputchips:not(.p-disabled).p-focus .p-variant-filled.p-inputchips-input {
        background: dt('inputchips.filled.focus.background');
    }

    .p-inputchips.p-disabled .p-inputchips-input {
        opacity: 1;
        background: dt('inputchips.disabled.background');
        color: dt('inputchips.disabled.color');
    }

    .p-inputchips-chip.p-chip {
        padding-top: calc(dt('inputchips.padding.y') / 2);
        padding-bottom: calc(dt('inputchips.padding.y') / 2);
        border-radius: dt('inputchips.chip.border.radius');
        transition:
            background dt('inputchips.transition.duration'),
            color dt('inputchips.transition.duration');
    }

    .p-inputchips-chip-item.p-focus .p-inputchips-chip {
        background: dt('inputchips.chip.focus.background');
        color: dt('inputchips.chip.focus.color');
    }

    .p-inputchips-input:has(.p-inputchips-chip) {
        padding-left: calc(dt('inputchips.padding.y') / 2);
        padding-right: calc(dt('inputchips.padding.y') / 2);
    }

    .p-inputchips-input-item {
        flex: 1 1 auto;
        display: inline-flex;
        padding-top: calc(dt('inputchips.padding.y') / 2);
        padding-bottom: calc(dt('inputchips.padding.y') / 2);
    }

    .p-inputchips-input-item input {
        border: 0 none;
        outline: 0 none;
        background: transparent;
        margin: 0;
        padding: 0;
        box-shadow: none;
        border-radius: 0;
        width: 100%;
        font-family: inherit;
        font-feature-settings: inherit;
        font-size: 1rem;
        color: inherit;
    }

    .p-inputchips-input-item input::placeholder {
        color: dt('inputchips.placeholder.color');
    }
`,classes:{root:function(e){var t=e.instance,n=e.props;return[`p-inputchips p-component p-inputwrapper`,{"p-disabled":n.disabled,"p-invalid":n.invalid,"p-focus":t.focused,"p-inputwrapper-filled":n.modelValue&&n.modelValue.length||t.inputValue&&t.inputValue.length,"p-inputwrapper-focus":t.focused}]},input:function(e){var t=e.props,n=e.instance;return[`p-inputchips-input`,{"p-variant-filled":t.variant?t.variant===`filled`:n.$primevue.config.inputStyle===`filled`||n.$primevue.config.inputVariant===`filled`}]},chipItem:function(e){var t=e.state,n=e.index;return[`p-inputchips-chip-item`,{"p-focus":t.focusedIndex===n}]},pcChip:`p-inputchips-chip`,chipIcon:`p-inputchips-chip-icon`,inputItem:`p-inputchips-input-item`}}),N={name:`BaseInputChips`,extends:_,props:{modelValue:{type:Array,default:null},max:{type:Number,default:null},separator:{type:[String,Object],default:null},addOnBlur:{type:Boolean,default:null},allowDuplicate:{type:Boolean,default:!0},placeholder:{type:String,default:null},variant:{type:String,default:null},invalid:{type:Boolean,default:!1},disabled:{type:Boolean,default:!1},inputId:{type:String,default:null},inputClass:{type:[String,Object],default:null},inputStyle:{type:Object,default:null},inputProps:{type:null,default:null},removeTokenIcon:{type:String,default:void 0},chipIcon:{type:String,default:void 0},ariaLabelledby:{type:String,default:null},ariaLabel:{type:String,default:null}},style:M,provide:function(){return{$pcInputChips:this,$parentInstance:this}}};function P(e){return R(e)||L(e)||I(e)||F()}function F(){throw TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`)}function I(e,t){if(e){if(typeof e==`string`)return z(e,t);var n={}.toString.call(e).slice(8,-1);return n===`Object`&&e.constructor&&(n=e.constructor.name),n===`Map`||n===`Set`?Array.from(e):n===`Arguments`||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)?z(e,t):void 0}}function L(e){if(typeof Symbol<`u`&&e[Symbol.iterator]!=null||e[`@@iterator`]!=null)return Array.from(e)}function R(e){if(Array.isArray(e))return z(e)}function z(e,t){(t==null||t>e.length)&&(t=e.length);for(var n=0,r=Array(t);n<t;n++)r[n]=e[n];return r}var B={name:`InputChips`,extends:N,inheritAttrs:!1,emits:[`update:modelValue`,`add`,`remove`,`focus`,`blur`],data:function(){return{inputValue:null,focused:!1,focusedIndex:null}},mounted:function(){console.warn(`Deprecated since v4. Use AutoComplete component instead with its typeahead property.`)},methods:{onWrapperClick:function(){this.$refs.input.focus()},onInput:function(e){this.inputValue=e.target.value,this.focusedIndex=null},onFocus:function(e){this.focused=!0,this.focusedIndex=null,this.$emit(`focus`,e)},onBlur:function(e){this.focused=!1,this.focusedIndex=null,this.addOnBlur&&this.addItem(e,e.target.value,!1),this.$emit(`blur`,e)},onKeyDown:function(e){var t=e.target.value;switch(e.code){case`Backspace`:t.length===0&&this.modelValue&&this.modelValue.length>0&&(this.focusedIndex===null?this.removeItem(e,this.modelValue.length-1):this.removeItem(e,this.focusedIndex));break;case`Enter`:case`NumpadEnter`:t&&t.trim().length&&!this.maxedOut&&this.addItem(e,t,!0);break;case`ArrowLeft`:t.length===0&&this.modelValue&&this.modelValue.length>0&&this.$refs.container.focus();break;case`ArrowRight`:e.stopPropagation();break;default:this.separator&&(this.separator===e.key||e.key.match(this.separator))&&this.addItem(e,t,!0);break}},onPaste:function(e){var t=this;if(this.separator){var n=this.separator.replace(`\\n`,`
`).replace(`\\r`,`\r`).replace(`\\t`,`	`),r=(e.clipboardData||window.clipboardData).getData(`Text`);if(r){var i=this.modelValue||[],a=r.split(n);a=a.filter(function(e){return t.allowDuplicate||i.indexOf(e)===-1}),i=[].concat(P(i),P(a)),this.updateModel(e,i,!0)}}},onContainerFocus:function(){this.focused=!0},onContainerBlur:function(){this.focusedIndex=-1,this.focused=!1},onContainerKeyDown:function(e){switch(e.code){case`ArrowLeft`:this.onArrowLeftKeyOn(e);break;case`ArrowRight`:this.onArrowRightKeyOn(e);break;case`Backspace`:this.onBackspaceKeyOn(e);break}},onArrowLeftKeyOn:function(){this.inputValue.length===0&&this.modelValue&&this.modelValue.length>0&&(this.focusedIndex=this.focusedIndex===null?this.modelValue.length-1:this.focusedIndex-1,this.focusedIndex<0&&(this.focusedIndex=0))},onArrowRightKeyOn:function(){this.inputValue.length===0&&this.modelValue&&this.modelValue.length>0&&(this.focusedIndex===this.modelValue.length-1?(this.focusedIndex=null,this.$refs.input.focus()):this.focusedIndex++)},onBackspaceKeyOn:function(e){this.focusedIndex!==null&&this.removeItem(e,this.focusedIndex)},updateModel:function(e,t,n){var r=this;this.$emit(`update:modelValue`,t),this.$emit(`add`,{originalEvent:e,value:t}),this.$refs.input.value=``,this.inputValue=``,setTimeout(function(){r.maxedOut&&(r.focused=!1)},0),n&&e.preventDefault()},addItem:function(e,t,n){if(t&&t.trim().length){var r=this.modelValue?P(this.modelValue):[];(this.allowDuplicate||r.indexOf(t)===-1)&&(r.push(t),this.updateModel(e,r,n))}},removeItem:function(e,t){if(!this.disabled){var n=P(this.modelValue),r=n.splice(t,1);this.focusedIndex=null,this.$refs.input.focus(),this.$emit(`update:modelValue`,n),this.$emit(`remove`,{originalEvent:e,value:r})}}},computed:{maxedOut:function(){return this.max&&this.modelValue&&this.max===this.modelValue.length},focusedOptionId:function(){return this.focusedIndex===null?null:`${this.$id}_inputchips_item_${this.focusedIndex}`}},components:{Chip:O}};function V(e){"@babel/helpers - typeof";return V=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},V(e)}function H(e,t){var n=Object.keys(e);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(e);t&&(r=r.filter(function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable})),n.push.apply(n,r)}return n}function U(e){for(var t=1;t<arguments.length;t++){var n=arguments[t]==null?{}:arguments[t];t%2?H(Object(n),!0).forEach(function(t){W(e,t,n[t])}):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(n)):H(Object(n)).forEach(function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(n,t))})}return e}function W(e,t,n){return(t=G(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function G(e){var t=K(e,`string`);return V(t)==`symbol`?t:t+``}function K(e,t){if(V(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(V(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var q=[`aria-labelledby`,`aria-label`,`aria-activedescendant`],J=[`id`,`aria-label`,`aria-setsize`,`aria-posinset`,`data-p-focused`],Y=[`id`,`disabled`,`placeholder`,`aria-invalid`];function X(e,l,u,f,h,g){var _=r(`Chip`);return p(),o(`div`,m({class:e.cx(`root`)},e.ptmi(`root`)),[a(`ul`,m({ref:`container`,class:e.cx(`input`),tabindex:`-1`,role:`listbox`,"aria-orientation":`horizontal`,"aria-labelledby":e.ariaLabelledby,"aria-label":e.ariaLabel,"aria-activedescendant":h.focused?g.focusedOptionId:void 0,onClick:l[5]||=function(e){return g.onWrapperClick()},onFocus:l[6]||=function(){return g.onContainerFocus&&g.onContainerFocus.apply(g,arguments)},onBlur:l[7]||=function(){return g.onContainerBlur&&g.onContainerBlur.apply(g,arguments)},onKeydown:l[8]||=function(){return g.onContainerKeyDown&&g.onContainerKeyDown.apply(g,arguments)}},e.ptm(`input`)),[(p(!0),o(c,null,n(e.modelValue,function(n,r){return p(),o(`li`,m({key:`${r}_${n}`,id:e.$id+`_inputchips_item_`+r,role:`option`,class:e.cx(`chipItem`,{index:r}),"aria-label":n,"aria-selected":!0,"aria-setsize":e.modelValue.length,"aria-posinset":r+1},{ref_for:!0},e.ptm(`chipItem`),{"data-p-focused":h.focusedIndex===r}),[t(e.$slots,`chip`,{class:d(e.cx(`pcChip`)),index:r,value:n,removeCallback:function(t){return e.removeOption(t,r)}},function(){return[s(_,{class:d(e.cx(`pcChip`)),label:n,removeIcon:e.chipIcon||e.removeTokenIcon,removable:``,unstyled:e.unstyled,onRemove:function(e){return g.removeItem(e,r)},pt:e.ptm(`pcChip`)},{removeicon:i(function(){return[t(e.$slots,e.$slots.chipicon?`chipicon`:`removetokenicon`,{class:d(e.cx(`chipIcon`)),index:r,removeCallback:function(e){return g.removeItem(e,r)}})]}),_:2},1032,[`class`,`label`,`removeIcon`,`unstyled`,`onRemove`,`pt`])]})],16,J)}),128)),a(`li`,m({class:e.cx(`inputItem`),role:`option`},e.ptm(`inputItem`)),[a(`input`,m({ref:`input`,id:e.inputId,type:`text`,class:e.inputClass,style:e.inputStyle,disabled:e.disabled||g.maxedOut,placeholder:e.placeholder,"aria-invalid":e.invalid||void 0,onFocus:l[0]||=function(e){return g.onFocus(e)},onBlur:l[1]||=function(e){return g.onBlur(e)},onInput:l[2]||=function(){return g.onInput&&g.onInput.apply(g,arguments)},onKeydown:l[3]||=function(e){return g.onKeyDown(e)},onPaste:l[4]||=function(e){return g.onPaste(e)}},U(U({},e.inputProps),e.ptm(`inputItemField`))),null,16,Y)],16)],16,q)],16)}B.render=X;var Z={name:`Chips`,extends:B,mounted:function(){console.warn(`Deprecated since v4. Use InputChips component instead.`)}};export{Z as t};