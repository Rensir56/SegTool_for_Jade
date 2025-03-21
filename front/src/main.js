import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import axios from './util/request.js'
import { VueDraggable } from 'vue-draggable-plus'

axios.defaults.headers.post['Content-Type'] = 'application/x-www-form-urlencoded';

const app = createApp(App)
app.config.globalProperties.$http = axios

app.use(router)
    .use(ElementPlus)
    .component('VueDraggable', VueDraggable)
    .mount('#app');
