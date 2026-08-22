# 中文旁白试听清单

只有配置 `MINIMAX_API_KEY` 后才执行：

```bash
cd server
PYTHONPATH=. python ../tools/smoke_minimax_narration.py
```

分别用耳机试听 `calm.mp3`、`documentary.mp3`、`story.mp3`，记录：

- 专名、地名和多音字是否准确；
- 句间停顿是否给行走留出观察时间；
- 情绪是否克制，不像广告或短视频配音；
- 户外 60% 音量下是否清楚、无爆音；
- 事实陈述与编辑推断的语气是否有区分；
- 最终采用的 preset、voice、emotion、speed、pitch 和文字稿哈希。

批准动作必须在后台试听页完成。它会再次核对当前文字稿哈希，成功上传公开版本后才更新路线引用；本地烟测文件不会自动进入媒体库。
