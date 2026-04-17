import{A as e,D as t,c as n,d as r,it as i,l as a,u as o,w as s,x as c}from"./_plugin-vue_export-helper-Bfi6r8i4.js";import{ut as l,x as u,y as d}from"./client-BCqwyZ4b.js";var f=u.extend({name:`tag`,style:`
    .p-tag {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: dt('tag.primary.background');
        color: dt('tag.primary.color');
        font-size: dt('tag.font.size');
        font-weight: dt('tag.font.weight');
        padding: dt('tag.padding');
        border-radius: dt('tag.border.radius');
        gap: dt('tag.gap');
    }

    .p-tag-icon {
        font-size: dt('tag.icon.size');
        width: dt('tag.icon.size');
        height: dt('tag.icon.size');
    }

    .p-tag-rounded {
        border-radius: dt('tag.rounded.border.radius');
    }

    .p-tag-success {
        background: dt('tag.success.background');
        color: dt('tag.success.color');
    }

    .p-tag-info {
        background: dt('tag.info.background');
        color: dt('tag.info.color');
    }

    .p-tag-warn {
        background: dt('tag.warn.background');
        color: dt('tag.warn.color');
    }

    .p-tag-danger {
        background: dt('tag.danger.background');
        color: dt('tag.danger.color');
    }

    .p-tag-secondary {
        background: dt('tag.secondary.background');
        color: dt('tag.secondary.color');
    }

    .p-tag-contrast {
        background: dt('tag.contrast.background');
        color: dt('tag.contrast.color');
    }
`,classes:{root:function(e){var t=e.props;return[`p-tag p-component`,{"p-tag-info":t.severity===`info`,"p-tag-success":t.severity===`success`,"p-tag-warn":t.severity===`warn`,"p-tag-danger":t.severity===`danger`,"p-tag-secondary":t.severity===`secondary`,"p-tag-contrast":t.severity===`contrast`,"p-tag-rounded":t.rounded}]},icon:`p-tag-icon`,label:`p-tag-label`}}),p={name:`BaseTag`,extends:d,props:{value:null,severity:null,rounded:Boolean,icon:String},style:f,provide:function(){return{$pcTag:this,$parentInstance:this}}};function m(e){"@babel/helpers - typeof";return m=typeof Symbol==`function`&&typeof Symbol.iterator==`symbol`?function(e){return typeof e}:function(e){return e&&typeof Symbol==`function`&&e.constructor===Symbol&&e!==Symbol.prototype?`symbol`:typeof e},m(e)}function h(e,t,n){return(t=g(t))in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n,e}function g(e){var t=_(e,`string`);return m(t)==`symbol`?t:t+``}function _(e,t){if(m(e)!=`object`||!e)return e;var n=e[Symbol.toPrimitive];if(n!==void 0){var r=n.call(e,t);if(m(r)!=`object`)return r;throw TypeError(`@@toPrimitive must return a primitive value.`)}return(t===`string`?String:Number)(e)}var v={name:`Tag`,extends:p,inheritAttrs:!1,computed:{dataP:function(){return l(h({rounded:this.rounded},this.severity,this.severity))}}},y=[`data-p`];function b(l,u,d,f,p,m){return s(),r(`span`,c({class:l.cx(`root`),"data-p":m.dataP},l.ptmi(`root`)),[l.$slots.icon?(s(),a(e(l.$slots.icon),c({key:0,class:l.cx(`icon`)},l.ptm(`icon`)),null,16,[`class`])):l.icon?(s(),r(`span`,c({key:1,class:[l.cx(`icon`),l.icon]},l.ptm(`icon`)),null,16)):o(``,!0),l.value!=null||l.$slots.default?t(l.$slots,`default`,{key:2},function(){return[n(`span`,c({class:l.cx(`label`)},l.ptm(`label`)),i(l.value),17)]}):o(``,!0)],16,y)}v.render=b;export{v as t};