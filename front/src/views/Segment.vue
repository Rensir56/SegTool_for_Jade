<template>
  <div class="hoalPage">
    <div class="segment-container">
      <!-- 左侧工具栏 -->
      <div class="tool-box">
        <!-- 上传pdf按钮与标题 -->
        <div class="title">
          <div>
            <el-icon style="font-size: 25px">
              <Document></Document>
            </el-icon>
            <el-upload ref="uploadRef" style="display: inline-block" :auto-upload="true" :show-file-list="false"
              :http-request="uploadPDF" :on-success="handlePdfSuccess" :on-error="handleUploadError">
              <template #trigger>
                <span style="font-size: 18px; font-weight: 550; cursor: pointer">
                  上传PDF
                </span>
              </template>
            </el-upload>
            <el-icon class="header-icon"></el-icon>
          </div>
        </div>

        <!-- 选项按钮 -->
        <div class="options-box">
          <div class="options-section">
            <span class="option" @click="updatePage">刷新</span>
            <span class="option" @click="reset">重置</span>
            <span :class="'option' + (clicks.length === 0 ? ' disabled' : '')" @click="undo">撤销</span>
            <span :class="'option' + (clickHistory.length === 0 ? ' disabled' : '')" @click="redo">恢复</span>
          </div>
          <div :class="'segmentation-button' +
            (lock || clicks.length === 0 ? ' disabled' : '')
            " @click="cutImage">
            分割
          </div>
          <div class="pagination" v-if="pdfFilename !== ''">
            <div class="page-button" @click="previousPage" :disabled="currentPage <= 1">
              上一页
            </div>

            <input v-if="handlePage === 1" type="number" v-model.number="jumpPage" @keydown.enter="Jump" :min="1"
              :max="totalPages" />
            <span v-if="handlePage === 0" @click="handlePage = 1" style="cursor: pointer">
              {{ currentPage }} / {{ totalPages }}
            </span>
            <div class="page-button" @click="nextPage" :disabled="currentPage >= totalPages">
              下一页
            </div>
          </div>
        </div>
      </div>

      <div class="pdf-box">
        <!-- pdf预览区 -->
        <div class="segment-box">
          <div v-if="pdfFilename === ''">
            <p>尚未上传PDF</p>
            <p>上传后将显示每页的图片</p>
          </div>
          <!-- pdf预览 -->
          <div class="segment-wrapper" :style="{ left: left + 'px' }">
            <img v-show="path" id="segment-image" :src="url" :style="{ width: w, height: h }" alt="加载失败"
              crossorigin="anonymous" @mousedown="handleMouseDown" @mouseenter="canvasVisible = true" @mouseout="() => {
                if (!this.clicks.length && !this.isEverything)
                  this.canvasVisible = false;
              }
                " />
            <canvas v-show="path && canvasVisible" id="segment-canvas" :width="originalSize.w"
              :height="originalSize.h"></canvas>
            <div id="point-box" :style="{ width: w, height: h }"></div>
          </div>
        </div>
      </div>
      <!-- 右侧工作区 -->
      <div class="work-box">
        <VueDraggable v-model="cutOuts" :animation="150" class="image-box">
          <div class="image-box-item" v-for="(item, index) in cutOuts" :key="item.image">
            <div class="image-box-item-title" v-if="!isEditing(item)" @click="startEditing(item, index)">
              {{ ImageName(item, index) }}
            </div>
            <input v-else type="text" class="image-box-item-title" v-model="editTitle" @blur="saveEditing(item)"
              @keyup.enter="saveEditing(item)" ref="editInput" />
            <el-icon class="image-box-item-icon" @click="removeImage(index)">
              <Close />
            </el-icon>
            <img alt="加载中" :src="item.image" />
            <input type="number" class="index-input" v-model.number="item.desiredIndex" @blur="updateIndex(item, index)"
              @keyup.enter="updateIndex(item, index)" />
          </div>
        </VueDraggable>
        <div class="operation-box">
          <div class="operation-buttons">
            <div class="operation-button" @click="confirmSaveImages">确认</div>
            <div class="operation-button" @click="clearImages">清空</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import throttle from "@/util/throttle";
import LZString from "lz-string";
import _ from 'lodash'; // 使用 lodash 库来实现节流
import {
  rleFrString,
  decodeRleCounts,
  decodeEverythingMask,
  getUniqueColor,
  cutOutImage,
  cutOutImageWithMaskColor,
  cutOutImageWithCategory,
} from "@/util/mask_utils";
import {
  ElCollapse,
  ElCollapseItem,
  ElScrollbar,
  ElMessage,
} from "element-plus";
import { Document, Close } from "@element-plus/icons-vue";
import { saveAs } from "file-saver";
import { ref } from "vue";
import { VueDraggable } from "vue-draggable-plus";

export default {
  name: "Segment",
  components: {
    ElCollapse,
    ElCollapseItem,
    ElScrollbar,
    Document,
    Close,
  },
  data() {
    return {
      image: null,
      jumpPage: 1,
      clicks: [],
      batchSize: 4,
      clickHistory: [],
      originalSize: { w: 0, h: 0 },
      w: 0,
      h: 0,
      left: 0,
      scale: 1,
      firstlock: false,
      url: null,
      path: null,
      loading: false,
      lock: false,
      canvasVisible: true,
      cutOuts: [],
      isEverything: false,
      pdfFilename: "", // 保存上传后的 PDF 文件名
      currentImage: null, // 当前选中的图片
      // selectedImages: [], // 保存被点击过的图片
      currentPage: 0, // 当前页号，初始为0
      totalPages: 0, // 总页数
      segmentationResults: {}, // 存储所有页面的分割结果
      pageLocks: {}, // 用于存储每个页面的锁状态
      preNum: 0, // 图像标号
      allowedChars: [
        "图",
        "零",
        "〇",
        "O",
        "o",
        "0",
        "一",
        "二",
        "三",
        "四",
        "五",
        "六",
        "七",
        "八",
        "九",
        "十",
      ],
      truncatedName: "图",
      isProcessing: false,
      protectvalid: false,
      handlePage: 0,
      editingItem: null, // 当前编辑的项
      editTitle: "",
    };
  },
  // created() {
  //   // this.loadSelectedImages();  // 在组件创建时加载图片数据
  //   this.loadCutOuts();
  // },
  mounted() {
    this.init();
  },
  methods: {
    async init() { },
    async uploadPDF({ file, onSuccess, onError }) {
      console.log("开始上传");
      const formData = new FormData();
      formData.append("pdf", file); // 确保这个 "pdf" 和后端代码匹配
      console.log("上传的文件:", file);

      this.$http
        .post('/api/go/upload', formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        })
        .then((response) => {
          console.log("上传成功:", response);

          // 检查 response 和 response.data
          if (response) {
            console.log("data:", response);
            // 检查 data.totalPages 是否存在
            if (typeof response.totalPages !== "undefined") {
              this.totalPages = response.totalPages; // 正确赋值
              console.log("pdf 页数是", this.totalPages);
            } else {
              console.error("totalPages 未找到:", response);
            }
          } else {
            console.error("响应数据不正确或为空:", response);
          }
          // 确保调用 onSuccess 回调函数
          onSuccess(response);
        })
        .catch((error) => {
          console.error("上传失败:", error);
          onError(error); // 调用 onError 回调，传递错误信息
        });
    },
    removeImage(index) {
      this.cutOuts.splice(index, 1);
      this.saveCutOuts(); // 保存数据到 localStorage
    },
    handleUploadError() {
      alert("上传失败");
      console.error("Error", arguments);
    },
    // 处理 PDF 上传成功
    async handlePdfSuccess(response) {
      console.log("pdf upload success");
      console.log("检查返回数据：");
      console.log(response);
      if (response && response.filename) {
        this.pdfFilename = response.filename;
        this.currentPage = 1;
        this.isProcessing = true; // 初始化时设置为true

        // 开始并行处理 PDF 页面的分割
        this.processAllPagesSegment(this.batchSize, false); // 这里假设一次处理3页，具体根据服务器性能调整；第一次执行不需要保护
      }
    },
    async processAllPagesSegment(batchSize, protectflag) {
      console.log("Parallel processing begins");
      const totalPages = this.totalPages;
      let currentPage = this.currentPage;
      // 新增 breakflag 定义
      let breakflag = false;
      let cnt = 0;
      while (currentPage <= totalPages) {
        const endPage = Math.min(currentPage + batchSize - 1, totalPages);
        for (let page = currentPage; page <= endPage; page++) {
          if (!(this.isProcessing || (protectflag && this.protectvalid))) {
            // isProcessing 用来中断旧进程，protectflag用来保护新进程，protectvalid代表旧进程结束新进程保护失效
            this.isProcessing = true;
            this.protectvalid = false;
            breakflag = true;
            console.log("break page", currentPage);
            break;
          }
          console.log("Segmenting page", page);
          // 等待每个页面处理完成后再继续处理下一个页面
          await this.uploadAndSegmentPage(page);
          cnt = cnt + 1;
          if (cnt == 1) {
            this.updatePage();
          }
          await new Promise((resolve) => setTimeout(resolve, 50)); // 50ms 延迟
        }
        if (breakflag) {
          break;
        }
        const shouldDelayNextBatch = this.shouldDelayNextBatch(
          currentPage + (batchSize + 1) / 2
        );
        if (shouldDelayNextBatch) {
          console.log("Pausing and waiting for user interaction");
          // 等待用户操作完成后继续
          await this.waitForUserInteraction(currentPage + (batchSize + 1) / 2);
        } else {
          console.log("Immediately starting the next batch");
        }
        // 更新 currentPage
        currentPage += batchSize;
      }
      console.log("All pages processed or waiting for user interaction.");
    },
    shouldDelayNextBatch(nextBatchPage) {
      // 判断当前页是否在一个batch中过半，或者是否在批次的开头
      return this.currentPage < nextBatchPage;
    },
    waitForUserInteraction(nextBatchPage) {
      return new Promise((resolve) => {
        const checkInterval = 1000; // 每1秒检查一次
        const intervalId = setInterval(() => {
          if (this.currentPage >= nextBatchPage) {
            clearInterval(intervalId);
            console.log("User has reached target page, resuming processing");
            resolve(); // 继续 while 循环
          }
        }, checkInterval);
      });
    },
    // 新增的Jump函数，用于跳转到指定页码
    async Jump() {
      const page = Math.max(1, Math.min(this.jumpPage, this.totalPages));
      await this.uploadImageFromPDF(page, false);
      this.handlePage = 0;
      // console.log(`Jumping to page ${currentPage}`);
      this.isProcessing = false; // 终止当前进程
      this.protectvalid = true;
      this.currentPage = page;
      this.processAllPagesSegment(this.batchSize, true); // 重新开始新的并行进程
    },
    async uploadAndSegmentPage(page) {
      // 检查是否已经上传过该页的图像，避免重复上传
      if (!this.segmentationResults[page]) {
        const path = await this.uploadImageFromPDF(page, false); // 获取并返回图像路径

        console.log("path is ", path);

        // 确保路径已被设置
        if (path) {
          const segmentationResult = await this.segmentEverything(path, page); // 使用局部的路径传递
          if (segmentationResult) {
            console.log("分割页", page);
            console.log("返回");
            console.log(segmentationResult);
            this.segmentationResults[page] = segmentationResult;
            console.log("当前数组为");
            console.log(this.segmentationResults);
          }
        } else {
          console.error(`Path not set correctly for page ${page}`);
        }
      }
    },
    // 获取指定页码的 PDF 页面图像并上传
    async uploadImageFromPDF(page, shouldShowImage) {
      console.log("uploadImageFromPDF begin");
      console.log("filename:", this.pdfFilename);
      console.log("page:", page);

      // 创建一个缓存对象来存储已经上传过的图片路径
      if (!this.imageCache) {
        this.imageCache = {};
      }

      try {
        // 获取页面图像
        const response = await fetch(
          `/api/go/show?filename=${this.pdfFilename}&page=${page}`
        );

        const data = await response.json();
        console.log("获取页面图像成功:", data);

        if (data && data.image) {
          // 生成一个唯一的键来标识这个图片
          const imageKey = `${this.pdfFilename}_page_${page}`;
          // 检查缓存中是否已经存在这个图片的路径
          if (this.imageCache[imageKey]) {
            console.log("图片已存在缓存中，直接返回路径");
            console.log("imageCache[imageKey]:", this.imageCache[imageKey]);
            // 执行 showImage 函数
            this.showImage(
              {
                path: this.imageCache[imageKey].path,
                src: this.imageCache[imageKey].src,
              },
              shouldShowImage
            );
            return this.imageCache[imageKey].path;
          }
          // 将 Base64 图片上传到服务器
          const uploadResult = await this.uploadImage(
            `data:image/png;base64,${data.image}`,
            shouldShowImage
          );
          // 将上传后的路径和 src 存储到缓存中
          this.imageCache[imageKey] = {
            path: uploadResult.path,
            src: uploadResult.src,
          };
          return uploadResult.path; // 返回图像路径
        }
      } catch (error) {
        console.error("Error getting page image:", error);
      }
    },
    // 上传图像
    async uploadImage(imageSrc, shouldShowImage) {
      try {
        // 将 Base64 数据转换为 Blob
        const blob = this.base64ToBlob(imageSrc.split(",")[1], "image/png");
        const fileName = `image-page-${this.currentPage}-${Date.now()}.png`;

        const formData = new FormData();
        formData.append("file", blob, fileName);

        // 上传图片
        const uploadResponse = await fetch('/api/fastapi/upload', {
          method: "POST",
          body: formData,
        });

        if (uploadResponse.ok) {
          const responseData = await uploadResponse.json();
          this.showImage(responseData, shouldShowImage);
          return responseData; // 返回路径
        } else {
          console.error("上传失败:", uploadResponse.statusText);
        }
      } catch (error) {
        console.error("上传过程出错:", error);
      }
    },
    // Base64 转 Blob
    base64ToBlob(base64, mimeType) {
      const byteCharacters = atob(base64);
      const byteNumbers = new Array(byteCharacters.length);

      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }

      const byteArray = new Uint8Array(byteNumbers);
      return new Blob([byteArray], { type: mimeType });
    },
    async nextPage() {
      if (this.currentPage < this.totalPages) {
        this.currentPage++;
        console.log("nextPage", this.currentPage);
        await this.updatePage();;
      }
    },
    async previousPage() {
      if (this.currentPage > 1) {
        this.currentPage--;
        console.log("previousPage", this.currentPage);
        await this.updatePage();
      }
    },
    async updatePage() {
      await this.uploadImageFromPDF(this.currentPage, true);
    },
    async addSegmentRes(pageId) {
      const result = this.segmentationResults[pageId];
      if (result) {
        this.cutOuts.push(...result);
      }
      console.log("cutOuts is ", this.cutOuts);
    },
    async showImage(res, flag) {
      console.log("showImage begin");
      console.log("上传成功", res);
      this.loadImage(res.path, res.src, flag); // 加入 resolve
    },
    loadImage(path, url, updateVariablesOnly) {
      let image = new Image();
      image.src = url;

      image.onload = () => {
        let w = image.width,
          h = image.height;
        let nw, nh;
        let body = document.querySelector(".segment-box");
        let mw = body.clientWidth,
          mh = body.clientHeight;
        let ratio = w / h;

        if (ratio * mh > mw) {
          nw = mw;
          nh = mw / ratio;
        } else {
          nh = mh;
          nw = ratio * mh;
        }

        // 更新计算后的尺寸
        this.originalSize = { w, h };

        if (updateVariablesOnly || !this.firstlock) {
          this.scale = nw / w;
          this.w = nw + "px";
          this.h = nh + "px";
          this.left = (mw - nw) / 2;
          this.url = url;
          this.path = path;
          this.firstlock = true;
        }

        console.log((this.scale > 1 ? "放大" : "缩小") + w + " --> " + nw);

        const img = document.getElementById("segment-image");

        // 确保图像在 DOM 中完全渲染后再处理 cutOuts
        const canvas = document.getElementById("segment-canvas");
        canvas.style.transform = `scale(${this.scale})`;

        // 确保 img.src 指向正确的 URL 后再进行 cutOuts 处理
        if (updateVariablesOnly) {
          console.log("添加页为", this.currentPage);
          this.addSegmentRes(this.currentPage);
          console.log("工作区更新完成", this.segmentationResults);
        }

        img.addEventListener("contextmenu", (e) => e.preventDefault());
        img.addEventListener("mousemove", throttle(this.handleMouseMove, 150));
      };
    },
    async segmentEverything(path, page) {
      // 只在当前页面需要处理时才检查锁
      if (this.pageLocks[page]) {
        return; // 当前页面正在处理或已经处理完成
      }

      this.pageLocks[page] = true; // 设置页面锁
      console.log("开始处理页", page);

      try {
        this.lock = true;
        this.reset(); // 重置状态
        console.log("开始分割页", page);
        console.log("yolo upload filename is", this.pdfFilename);

        let response; // 在外层作用域定义 response 变量

        try {
          response = await this.$http.post("http://10.22.125.155:8005/uploadimg", {
            path: path.replace(/\\/g, "/"),
            page: page,
            filename: this.pdfFilename,
          }, {
            headers: {
              "Content-Type": "application/json",
            },
          });
          console.log(response.data);
        } catch (error) {
          console.error("Error occurred:", error.response ? error.response.data : error);
        }

        console.log("path is: ", path);
        console.log("upload yolo res is ", response); // 现在 response 在外层作用域中定义，可以正常使用

        let res;
        try {
          res = await this.$http.post(`http://10.22.125.155:8005/segmentimg`, {
            pageId: page, // 将pageId作为请求体传递
            filename: this.pdfFilename, // 直接传递 filename
          }, {
            headers: {
              "Content-Type": "application/json",
            },
          });
          console.log(res);
        } catch (error) {
          // console.error("Error occurred:", error.res ? error.res.data : error);
        }

        console.log("finish segment in page", page);
        console.log("segment yolo res is ", res);
        this.segmentationResults[page] = res.images;
      } catch (err) {
        console.error(err);
        this.$message.error("生成失败");
      } finally {
        this.pageLocks[page] = false; // 释放页面锁
        this.lock = false;
      }
    },
    drawCanvas(shape, arr) {
      let height = shape[0],
        width = shape[1];
      console.log("height: ", height, " width: ", width);
      let canvas = document.getElementById("segment-canvas"),
        canvasCtx = canvas.getContext("2d"),
        imgData = canvasCtx.getImageData(0, 0, width, height),
        pixelData = imgData.data;
      let i = 0;
      for (let x = 0; x < width; x++) {
        for (let y = 0; y < height; y++) {
          if (arr[i++] === 0) {
            // 如果是0，是背景，遮住
            pixelData[0 + (width * y + x) * 4] = 40;
            pixelData[1 + (width * y + x) * 4] = 40;
            pixelData[2 + (width * y + x) * 4] = 40;
            pixelData[3 + (width * y + x) * 4] = 190;
          } else {
            pixelData[3 + (width * y + x) * 4] = 0;
          }
        }
      }
      canvasCtx.putImageData(imgData, 0, 0);
    },
    drawEverythingCanvas(shape, arr) {
      const height = shape[0],
        width = shape[1];
      console.log("height: ", height, " width: ", width);
      let canvas = document.getElementById("segment-canvas"),
        canvasCtx = canvas.getContext("2d"),
        imgData = canvasCtx.getImageData(0, 0, width, height),
        pixelData = imgData.data;
      const colorMap = {};
      let i = 0;
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const category = arr[i++];
          const color = getUniqueColor(category, colorMap);
          pixelData[0 + (width * y + x) * 4] = color.r;
          pixelData[1 + (width * y + x) * 4] = color.g;
          pixelData[2 + (width * y + x) * 4] = color.b;
          pixelData[3 + (width * y + x) * 4] = 150;
        }
      }
      // 开始分割每一个mask的图片
      const image = document.getElementById("segment-image");
      Object.keys(colorMap).forEach((category) => {
        cutOutImageWithCategory(
          this.originalSize,
          image,
          arr,
          category,
          (blob) => {
            const url = URL.createObjectURL(blob);
            this.cutOuts = [url, ...this.cutOuts];
            this.saveCutOuts();
          }
        );
      });
    },
    getClick(e) {
      let click = {
        x: e.offsetX,
        y: e.offsetY,
      };
      const imageScale = this.scale;
      click.x /= imageScale;
      click.y /= imageScale;
      if (e.which === 3) {
        // 右键
        click.clickType = 0;
      } else if (e.which === 1 || e.which === 0) {
        // 左键
        click.clickType = 1;
      }
      return click;
    },
    handleMouseMove(e) {
      if (this.isEverything) {
        // 分割所有模式，返回
        return;
      }
      if (this.clicks.length !== 0) {
        // 选择了点
        return;
      }
      if (this.lock) {
        return;
      }
      this.lock = true;
      let click = this.getClick(e);
      requestIdleCallback(() => {
        this.getMask([click]);
      });
    },
    handleMouseDown(e) {
      e.preventDefault();
      e.stopPropagation();
      if (e.button === 1) {
        return;
      }
      // 如果是“分割所有”模式，返回
      if (this.isEverything) {
        return;
      }
      if (this.lock) {
        return;
      }
      this.lock = true;
      let click = this.getClick(e);
      this.placePoint(e.offsetX, e.offsetY, click.clickType);
      this.clicks.push(click);
      requestIdleCallback(() => {
        this.getMask();
      });
    },
    placePoint(x, y, clickType) {
      let box = document.getElementById("point-box");
      let point = document.createElement("div");
      point.className = "segment-point" + (clickType ? "" : " negative");
      point.style = `position: absolute;
                      width: 10px;
                      height: 10px;
                      border-radius: 50%;
                      background-color: ${clickType ? "#409EFF" : "#F56C6C "};
                      left: ${x - 5}px;
                      top: ${y - 5}px`;
      // 点的id是在clicks数组中的下标索引
      point.id = "point-" + this.clicks.length;
      box.appendChild(point);
    },
    removePoint(i) {
      const selector = "point-" + i;
      let point = document.getElementById(selector);
      if (point != null) {
        point.remove();
      }
    },
    getMask(clicks) {
      // 如果clicks为空，则是mouse move产生的click
      if (clicks == null) {
        clicks = this.clicks;
      }
      const data = {
        path: this.path,
        clicks: clicks,
      };
      console.log(data);
      // 使用节流函数控制请求频率
      const throttledRequest = _.throttle(() => {
        this.$http
          .post("/api/fastapi/segment", data, {
            headers: {
              "Content-Type": "application/json",
            },
          })
          .then((res) => {
            const shape = res.shape;
            const maskenc = LZString.decompressFromEncodedURIComponent(res.mask);
            const decoded = rleFrString(maskenc);
            this.drawCanvas(shape, decodeRleCounts(shape, decoded));
            this.lock = false;
          })
          .catch((err) => {
            console.error(err);
            this.$message.error("生成失败");
            this.lock = false;
          });
      }, 400); // 设置节流时间为 200 毫秒

      throttledRequest();
    },
    reset() {
      // 清除所有点
      for (let i = 0; i < this.clicks.length; i++) {
        this.removePoint(i);
      }
      this.clicks = [];
      this.clickHistory = [];
      // this.cutOuts = []; // 清空已经提取出来的图片
      // this.saveCutOuts();
      this.isEverything = false; // 确保isEverything被重置
      this.lock = false; // 确保lock被解锁
      this.clearCanvas();
    },
    undo() {
      if (this.clicks.length === 0) return;
      const idx = this.clicks.length - 1;
      const click = this.clicks[idx];
      this.clickHistory.push(click);
      this.clicks.splice(idx, 1);
      this.removePoint(idx);
      if (this.clicks.length) {
        this.getMask();
      } else {
        this.clearCanvas();
      }
    },
    redo() {
      if (this.clickHistory.length === 0) return;
      const idx = this.clickHistory.length - 1;
      const click = this.clickHistory[idx];
      console.log(this.clicks, this.clickHistory, click);
      this.placePoint(
        click.x * this.scale,
        click.y * this.scale,
        click.clickType
      );
      this.clicks.push(click);
      this.clickHistory.splice(idx, 1);
      this.getMask();
    },
    clearCanvas() {
      let canvas = document.getElementById("segment-canvas");
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    },
    cutImage() {
      if (this.lock || this.clicks.length === 0) {
        return;
      }

      const canvas = document.getElementById("segment-canvas");
      const image = document.getElementById("segment-image");
      const { w, h } = this.originalSize;

      cutOutImage(this.originalSize, image, canvas, (blob) => {
        const url = URL.createObjectURL(blob);
        // 获取之前截断的部分 A
        const truncatedName = this.truncatedName;
        // 获取数组中的位置，生成 B 部分
        const index = this.cutOuts.length + 1; // 获取新元素在 cutOuts 中的位置
        // 生成最终的 name = A-B
        // const name = `${truncatedName}，${index}`;
        // 创建包含 image 和 name 的新对象
        const newCutOut = {
          image: url,
          name: truncatedName,
        };
        // 将新对象添加到 cutOuts 数组中
        this.cutOuts = [newCutOut, ...this.cutOuts];
        this.saveCutOuts();
        // 如果需要，可以保留 URL 以供后续使用
        // URL.revokeObjectURL(url);
      });

      // 清除锚点
      this.clicks = [];
      this.updatePoints();
    },
    updatePoints() {
      const pointBox = document.getElementById("point-box");
      if (pointBox) {
        pointBox.innerHTML = ""; // 清空锚点容器内容
      }
    },
    openInNewTab(src) {
      window.open(src, "_blank");
    },
    clearImages() {
      if (this.cutOuts.length > 0) {
        this.$confirm("确认要清空所有图片吗？", "警告", {
          confirmButtonText: "确认",
          cancelButtonText: "取消",
          type: "warning",
        })
          .then(() => {
            // 用户确认清空
            // this.selectedImages = [];
            // this.saveSelectedImages();
            this.currentImage = null;
            this.cutOuts = []; // 清空 image-box 中的卡片
            this.saveCutOuts();
            this.$message.success("图片已清空");
          })
          .catch(() => {
            // 用户取消清空
            this.$message.info("操作已取消");
          });
      } else {
        this.$message.info("没有图片需要清空");
      }
    },
    async confirmSaveImages() {
      try {
        // 使用 showDirectoryPicker 打开文件夹选择器
        const directoryHandle = await window.showDirectoryPicker();

        // 遍历 cutOuts 数组，依次保存每个图片
        for (const [index, cutOut] of this.cutOuts.entries()) {
          const { image: imageUrl } = cutOut;
          try {
            if (!imageUrl) {
              console.error("无效的图片 URL:", imageUrl);
              continue; // 如果 imageUrl 是无效的，跳过此循环迭代
            }

            const response = await fetch(imageUrl);

            if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
            }

            const blob = await response.blob();

            // 使用原有逻辑生成文件名
            const truncatedName = this.ImageName(cutOut, index);
            if (!truncatedName) {
              console.error("生成的文件名无效:", truncatedName);
              continue; // 如果生成的文件名无效，跳过此循环迭代
            }

            const fileName = `${truncatedName}.png`; // 可以根据图片实际格式调整

            // 获取文件句柄
            const fileHandle = await directoryHandle.getFileHandle(fileName, {
              create: true,
            });
            const writableStream = await fileHandle.createWritable();

            // 写入文件内容
            await writableStream.write(blob);
            await writableStream.close();
          } catch (error) {
            console.error("下载或保存图片失败:", error);
          }
        }

        ElMessage.success("保存成功");
        // 清空 cutOuts 数组并保存
        this.cutOuts = [];
        this.saveCutOuts();
        // 释放 free 掉 this.segmentationResults[this.currentPage]，避免内存泄漏
        if (this.segmentationResults && this.segmentationResults[this.currentPage]) {
          this.segmentationResults[this.currentPage] = null;
        }
      } catch (error) {
        console.error("文件夹选择失败或保存失败:", error);
      }
    },
    // 从 image 或 name 中截断出 A 部分
    getTruncatedName(name) {
      let truncatedName = "";

      for (let i = 0; i < name.length; i++) {
        if (this.allowedChars.includes(name[i])) {
          truncatedName += name[i];
        } else {
          break; // 出现不允许的字符，截断
        }
      }
      // this.preNum = this.chineseToNumber(truncatedName.replace(/图/, ''));
      this.truncatedName = truncatedName;
      return truncatedName;
    },
    // 截断并格式化名称
    ImageName(item, index) {
      // 调用 getTruncatedName 来获取截断后的 A 部分
      const truncatedName = this.getTruncatedName(item.name);
      // 组合截断后的名称和序号
      return `${truncatedName}-${index + 1}`;
    },
    saveCutOuts() {
      localStorage.setItem("cutOuts", JSON.stringify(this.cutOuts));
    },
    loadCutOuts() {
      const storedCutOuts = localStorage.getItem("cutOuts");
      if (storedCutOuts) {
        this.cutOuts = JSON.parse(storedCutOuts);
      }
    },
    isEditing(item) {
      return this.editingItem === item;
    },
    startEditing(item, index) {
      this.editingItem = item; // 设置当前正在编辑的项
      this.editTitle = this.ImageName(item, index); // 初始化编辑框内容为当前名称
      this.$nextTick(() => {
        const editInput = this.$refs.editInput[0];
        if (editInput) {
          editInput.focus();
        }
      });
    },

    // 保存编辑内容
    saveEditing(item) {
      if (this.editingItem) {
        item.name = this.editTitle; // 更新 item 的 name
        // 遍历cutOuts，更新每个cutOuts[index].name = this.editTitle
        this.cutOuts.forEach((cutOut, index) => {
          cutOut.name = this.ImageName(item, index);
        });
        this.editingItem = null; // 退出编辑模式
        this.saveCutOuts(); // 保存 cutOuts
      }
    },
    updateIndex(item, currentIndex) {
      // 更新索引
      const desiredIndex = item.desiredIndex - 1; // 输入的数字对应数组的索引
      if (desiredIndex >= 0 && desiredIndex < this.cutOuts.length && desiredIndex !== currentIndex) {
        // 移动元素到指定位置
        this.cutOuts.splice(currentIndex, 1);
        this.cutOuts.splice(desiredIndex, 0, item);
      }
      // 重置 desiredIndex
      item.desiredIndex = null;
    },
  },
};
</script>

<style scoped lang="scss">
.hoalPage {
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  position: absolute;
  background: linear-gradient(to bottom, #00487f 0%, #00487f81 100%);
}

/* 整个页面 */
.segment-container {
  /* background: linear-gradient(to bottom, #00487f 0%, #00487f81 100%); */
  background-color: white;
  box-shadow: 0 0 20px rgb(52, 52, 52);
  border-radius: 10px;
  position: absolute;
  top: 2.5vh;
  left: 2vw;
  right: 2vw;
  bottom: 2.5vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
}

/* 左侧工具栏 */
.tool-box {
  background-color: #00487f;
  height: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-top-left-radius: 10px;
  border-bottom-left-radius: 10px;
  /* justify-content: center;
  align-items: center; */

  .title {
    background-color: rgb(189, 0, 0);
    color: white;
    box-sizing: border-box;
    height: 15%;
    padding-top: 20%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    transition: 0.3s;
  }

  .title:hover {
    color: white;
    box-shadow: 0 0 5px rgb(150, 150, 150);
    /* transform: translateX(5px); */
    transform: scale(1.05);
  }

  .options-box {
    flex: 1;
    width: 100%;
    display: flex;
    flex-direction: column;
    /* justify-content: center; */
    align-items: center;

    .options-section {
      /* background-color: #F56C6C; */
      height: 36%;
      /* margin-left: 0.5vw; */
      /* padding: 0.5vh; */
      width: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      align-items: center;
      box-sizing: border-box;

      .option {
        background-color: #006abb00;
        color: white;
        box-sizing: border-box;
        height: 25%;
        width: 100%;
        font-size: 100%;
        padding: 10px;
        cursor: pointer;
        display: flex;
        justify-content: center;
        align-items: center;
        transition: 0.3s;
      }

      .option:hover {
        background-color: rgb(100, 188, 255);
        box-shadow: 0 0 5px rgb(150, 150, 150);
        /* transform: translateX(5px); */
        transform: scale(1.05);
      }

      .option.disabled {
        color: gray;
        cursor: not-allowed;
      }
    }

    .segmentation-button {
      /* box-sizing: border-box; */
      height: 9%;
      width: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
      background-color: #006abb00;
      color: white;
      font-size: 100%;
      cursor: pointer;
      transition: 0.3s;
    }

    .segmentation-button:hover {
      background-color: rgb(100, 188, 255);
      box-shadow: 0 0 5px rgb(150, 150, 150);
      transform: scale(1.05);
    }

    .segmentation-button.disabled {
      color: gray;
      cursor: not-allowed;
    }

    .pagination {
      background-color: #006abb00;
      color: white;
      /* height: 25%; */
      flex: 1;
      width: 100%;
      display: flex;
      justify-content: flex-end;
      flex-direction: column;
      align-items: center;
      /* justify-content: center; */
      /* padding: 20px; */
      gap: 2vh;

      .page-button {
        background-color: #006abb00;
        color: white;
        font-size: 100%;
        width: 100%;
        height: 7vh;
        display: flex;
        justify-content: center;
        align-items: center;
        /* border: 3px solid lightgray; */
        /* border-radius: 1vh; */
        margin-left: 0.5vw;
        margin-right: 0.5vw;
        transition: 0.3s;
      }

      .page-button:hover {
        background-color: rgb(100, 188, 255);
        box-shadow: 0 0 5px rgb(150, 150, 150);
        transform: scale(1.05);
        cursor: pointer;
      }
    }

    .pagination input {
      width: 70%;
    }
  }
}

.pdf-box {
  /* background-color:white; */
  box-sizing: border-box;
  width: 40%;
  height: 100%;
  overflow: hidden;
  box-sizing: border-box;
  /* padding: 1vh; */
  display: flex;
  flex-direction: column;

  .segment-box {
    box-sizing: border-box;
    flex: 1;
    width: 100%;
    padding: 1vh;
    position: relative;
    box-shadow: 0 5px 5px -5px rgb(150, 150, 150);

    .segment-wrapper {
      position: absolute;
      left: 0;
      top: 0;
      /* margin-left: calc(220px);
      width: calc(100% - 220px);
      height: calc(100vh - 80px); */
    }

    #segment-canvas {
      position: absolute;
      left: 0;
      top: 0;
      pointer-events: none;
      transform-origin: left top;
      z-index: 1;
    }

    #point-box {
      position: absolute;
      left: 0;
      top: 0;
      z-index: 2;
      pointer-events: none;
    }

    .segment-point {
      position: absolute;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background-color: #409eff;
    }

    .segment-point.negative {
      background-color: #f56c6c;
    }
  }
}

/* 右侧工作区 */
.work-box {
  /* background-color: white; */
  box-sizing: border-box;
  height: 100%;
  width: 55%;
  /* border-radius: 2vh;   */
  /* box-shadow: 0 0 5px rgb(150, 150, 150); */
  border-left: 1px solid rgb(0, 0, 0);
  box-sizing: border-box;
  border-top-right-radius: 10px;
  border-bottom-right-radius: 10px;
  /* padding: 1vh; */

  .index-input {
    position: absolute;
    bottom: 0;
    right: 0;
    width: 30px;
    height: 30px;
    text-align: center;
    border: 1px solid #ccc;
    border-radius: 4px;
  }

  .image-box {
    position: relative;
    box-sizing: border-box;
    width: 100%;
    height: 90%;
    box-shadow: 0 5px 5px -5px rgb(150, 150, 150);
    display: flex;
    flex-wrap: wrap;
    overflow-y: hidden;

    .image-box-item {
      position: relative;
      box-sizing: border-box;
      width: 27vh;
      height: 27vh;
      margin: 2vh 0vw 1vh 2vw;
      box-shadow: 0 0 5px rgb(150, 150, 150);
      overflow: hidden;
      display: flex;
      justify-content: center;
      align-items: center;
      background-color: #00487f;
      /* flex-shrink: 0; */
    }

    .image-box-item-icon {
      font-size: 4vh;
      color: gray;
      position: absolute;
      top: 0px;
      right: 0px;
      padding: 0px;
      cursor: pointer;
      z-index: 10;
      opacity: 0;
      /* 初始状态隐藏 */
      transition: opacity 0.3s ease;
    }

    .image-box-item:hover .image-box-item-icon {
      opacity: 1;
    }

    .image-box-item-icon:hover {
      color: red;
    }

    .image-box-item-title {
      position: absolute;
      top: 0px;
      left: 0px;
      width: auto;
      height: 3.5vh;
      background-color: rgba(200, 200, 200, 0.6);
      color: black;
      padding: 0px 3px;
      border-top-left-radius: 0.5vh;
      font-size: 2.5vh;
      z-index: 20;
    }

    .image-box-item img {
      max-width: 90%;
      max-height: 90%;
      object-fit: contain;
    }

    .image-box-item:hover {
      box-shadow: 0 0 15px rgb(125, 125, 125);
      cursor: pointer;
    }
  }

  .image-box::-webkit-scrollbar-thumb {
    background-color: #999;
    border-radius: 1vw;
  }

  .image-box::-webkit-scrollbar {
    width: 1vh;
  }

  .image-box:hover {
    overflow-y: overlay;
  }

  .operation-box {
    box-sizing: border-box;
    width: 100%;
    height: 10%;
    padding: 2vh 0.5vw 2vh 1vw;
    display: flex;
    flex-direction: row;
    justify-content: space-between;

    .operation-buttons {
      box-sizing: border-box;
      height: 100%;
      width: 100%;
      display: flex;
      flex-direction: row;
      justify-content: space-between;
      align-items: center;
      gap: 2vw;

      .counter-container {
        display: flex;
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
        height: 100%;
        width: 100%;
        gap: 5px;

        .counter-box {
          display: flex;
          flex-direction: row;
          justify-content: center;
          align-items: center;
          height: 100%;
          width: 70%;
        }

        .counter-input {
          width: 100%;
          height: 100%;
        }
      }

      .operation-button {
        height: 100%;
        width: 100%;
        background-color: #00487f;
        color: white;
        font-size: 17px;
        cursor: pointer;
        border-radius: 1vh;
        transition: 0.3s;
        display: flex;
        justify-content: center;
        align-items: center;
      }

      .operation-button:hover {
        background-color: rgb(100, 188, 255);
      }

      .operation-button.disabled {
        color: lightgray;
        cursor: not-allowed;
      }
    }
  }
}
</style>