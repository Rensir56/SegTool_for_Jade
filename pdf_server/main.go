package main

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

func main() {
	currentDir, err := os.Getwd()
	if err != nil {
		log.Fatalf("Error getting working directory: %v", err)
	}
	log.Printf("Current working directory: %s", currentDir)

	// 修改路径为 '/api/go/upload' 和 '/api/go/show'
	http.HandleFunc("/upload", uploadHandler)
	http.HandleFunc("/show", showHandler)

	// 在所有网络接口上监听 3001 端口
	log.Println("Starting server on 0.0.0.0:3001")
	err = http.ListenAndServe("0.0.0.0:3001", nil)
	if err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

func uploadHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == "OPTIONS" {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method != "POST" {
		http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
		return
	}

	log.Println("Handling POST request")
	file, header, err := r.FormFile("pdf")
	if err != nil {
		log.Println("Error reading PDF file:", err)
		http.Error(w, "Error reading PDF file", http.StatusBadRequest)
		return
	}
	defer file.Close()

	log.Println("Received file:", header.Filename)
	pdfPath := filepath.Join("uploads", header.Filename)
	out, err := os.Create(pdfPath)
	if err != nil {
		log.Println("Error creating PDF file:", err)
		http.Error(w, "Error creating PDF file", http.StatusInternalServerError)
		return
	}
	defer out.Close()

	_, err = io.Copy(out, file)
	if err != nil {
		log.Println("Error saving PDF file:", err)
		http.Error(w, "Error saving PDF file", http.StatusInternalServerError)
		return
	}

	log.Println("File saved:", pdfPath)

	// Get the PDF page count
	totalPages, err := getPDFPageCount(header.Filename)
	if err != nil {
		log.Printf("getPDFPageCount error: %v", err)
		http.Error(w, "Error getting PDF page count", http.StatusInternalServerError)
		return
	}

	// Return the filename and total page count
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Write([]byte(fmt.Sprintf(`{"filename": "%s", "totalPages": %d}`, header.Filename, totalPages)))
}

func showHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == "OPTIONS" {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method != "GET" {
		http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
		return
	}

	// Add CORS headers for actual response
	w.Header().Set("Access-Control-Allow-Origin", "*")

	filename := r.URL.Query().Get("filename")
	pageStr := r.URL.Query().Get("page")

	if filename == "" || pageStr == "" {
		http.Error(w, "Missing filename or page parameter", http.StatusBadRequest)
		return
	}

	// 将 pageStr 转换为整数类型
	page, err := strconv.Atoi(pageStr)
	if err != nil {
		http.Error(w, "Invalid page number", http.StatusBadRequest)
		return
	}

	// Convert the specified page to an image
	imgPath, err := convertPDFPageToImage(filename, page)
	if err != nil {
		log.Printf("convertPDFPageToImage error: %v", err)
		http.Error(w, "Error converting PDF to image", http.StatusInternalServerError)
		return
	}
	defer os.Remove(imgPath)

	// Convert the image to Base64
	base64Img, err := imageToBase64(imgPath)
	if err != nil {
		log.Printf("imageToBase64 error: %v", err)
		http.Error(w, "Error converting image to Base64", http.StatusInternalServerError)
		return
	}

	response := fmt.Sprintf(`{"image": "%s"}`, base64Img)
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(response))
}

func getPDFPageCount(pdfFilename string) (int, error) {
	pdfPath := filepath.Join("uploads", pdfFilename)

	// Prepare the command to get PDF page count
	cmd := exec.Command("pdfinfo", pdfPath)
	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	// Execute the command
	err := cmd.Run()
	if err != nil {
		return 0, fmt.Errorf("pdfinfo error: %v, stderr: %s", err, stderr.String())
	}

	// Parse the output to find the number of pages
	output := stdout.String()
	lines := strings.Split(output, "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "Pages:") {
			fields := strings.Fields(line)
			if len(fields) > 1 {
				pageCount, err := strconv.Atoi(fields[1])
				if err != nil {
					return 0, fmt.Errorf("error parsing page count: %v", err)
				}
				return pageCount, nil
			}
		}
	}

	return 0, fmt.Errorf("page count not found in pdfinfo output")
}

func convertPDFPageToImage(pdfFilename string, page int) (string, error) {
	pdfPath := filepath.Join("uploads", pdfFilename)
	outputDir := "uploads" // 保存生成的图像的目录
	os.MkdirAll(outputDir, os.ModePerm)

	// 构建输出文件前缀路径
	outputBaseName := strings.TrimSuffix(filepath.Base(pdfPath), filepath.Ext(pdfPath))
	outputPath := filepath.Join(outputDir, fmt.Sprintf("%s-page-%d", outputBaseName, page))

	// 使用 -singlefile 确保生成的文件名唯一
	cmd := exec.Command("pdftoppm", "-png", "-f", strconv.Itoa(page), "-l", strconv.Itoa(page), "-singlefile", pdfPath, outputPath)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	log.Printf("Running command: %s", cmd.String())
	err := cmd.Run()
	if err != nil {
		return "", fmt.Errorf("pdftoppm error: %v, stderr: %s", err, stderr.String())
	}

	// 生成的文件名为 outputPath.png
	imageFile := outputPath + ".png"
	if _, err := os.Stat(imageFile); os.IsNotExist(err) {
		return "", fmt.Errorf("image file not found: %s", imageFile)
	}

	log.Printf("Generated image file: %s", imageFile)
	return imageFile, nil
}

func imageToBase64(imgPath string) (string, error) {
	imgFile, err := os.Open(imgPath)
	if err != nil {
		return "", fmt.Errorf("error opening image file %s: %v", imgPath, err)
	}
	defer imgFile.Close()

	buf := new(bytes.Buffer)
	_, err = buf.ReadFrom(imgFile)
	if err != nil {
		return "", fmt.Errorf("error reading image file %s: %v", imgPath, err)
	}

	base64Str := base64.StdEncoding.EncodeToString(buf.Bytes())
	if base64Str == "" {
		return "", fmt.Errorf("base64 encoding resulted in an empty string for file %s", imgPath)
	}

	return base64Str, nil
}