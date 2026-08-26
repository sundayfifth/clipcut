# ฟอนต์

`google-sans.woff2` — Google Sans variable font (wght 400–700) ภายใต้ SIL Open Font License 1.1
ดูสัญญาอนุญาตเต็มใน `OFL.txt`

subset ไว้เฉพาะที่ UI ใช้: ละติน, ตัวเลข, **อักษรไทยครบ 87 ตัว**, เครื่องหมายวรรคตอน, ลูกศร
เก็บ GPOS ไว้ทั้งหมดเพราะภาษาไทยต้องใช้จัดตำแหน่งวรรณยุกต์

4.62 MB → 111 KB สร้างใหม่ได้ด้วย fontTools:

```
pyftsubset GoogleSans-VariableFont_GRAD,opsz,wght.ttf \
  --output-file=google-sans.woff2 --flavor=woff2 \
  --unicodes="U+0000-00FF,U+0E00-0E7F,U+2000-206F,U+2713" \
  --layout-features='*'
```
