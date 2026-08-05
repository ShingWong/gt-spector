# DXVK Readback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GPU→CPU frame readback to the DXVK offscreen swapchain, writing raw frames to POSIX shared memory for consumption by the Python gt-spector viewer.

**Architecture:** In `dxvk_presenter.cpp::presentImage()`, submit a `vkCmdCopyImageToBuffer` command buffer to the graphics queue after the game's render (queue ordering — no wait semaphores needed). Signal a fence. On the next frame, wait for the fence, map the staging buffer, and `memcpy` to `/dev/shm/gt-spector-<ID>-frame`. Python reads via mmap.

**Tech Stack:** C++ (DXVK presenter), Vulkan, POSIX shared memory (`shm_open`), Python (mmap + numpy)

## Global Constraints

- `vkQueueSubmit` with `waitSemaphoreCount > 0` **crashes** on RADV 25.0.7 + libvulkan 1.4.309 — all readback submits MUST use waitSemaphoreCount=0 (queue ordering is sufficient)
- SHM region name from env var `GT_SPECTOR_SHM_ID` (default "0"): `/dev/shm/gt-spector-<ID>-frame`
- SHM format: 16-byte header (uint64 frame_counter, uint32 width, uint32 height) + raw BGRA pixel data
- DXVK build source at `/tmp/dxvk-source-2.5.3/`, build in `build-win64/`
- Python package at `/home/swong/dls/gt-spector/`

---

### Task 1: DXVK Presenter — Readback Infrastructure

**Files:**
- Modify: `/tmp/dxvk-source-2.5.3/src/dxvk/dxvk_presenter.h` — add fields
- Modify: `/tmp/dxvk-source-2.5.3/src/dxvk/dxvk_presenter.cpp` — create/destroy resources

**Interfaces:**
- Consumes: existing offscreen swapchain fields `m_offscreen`, `m_images`, `m_offscreenMemory`
- Produces: command pool, staging buffers, staging memory, readback fences per swapchain image

- [ ] **Step 1: Add fields to dxvk_presenter.h**

After `std::vector<VkDeviceMemory> m_offscreenMemory;`, add:

```cpp
    VkCommandPool                 m_offscreenCmdPool    = VK_NULL_HANDLE;
    std::vector<VkBuffer>         m_offscreenStagingBuf;
    std::vector<VkDeviceMemory>   m_offscreenStagingMem;
    std::vector<VkFence>          m_offscreenReadbackFence;
```

Also add a private method declaration:
```cpp
    VkResult createOffscreenReadback();
    void     destroyOffscreenReadback();
```

- [ ] **Step 2: Add createOffscreenReadback() implementation**

In `dxvk_presenter.cpp`, add the implementation. This creates a command pool, one staging buffer + fence per swapchain image:

```cpp
VkResult DxvkPresenter::createOffscreenReadback() {
  // Command pool
  VkCommandPoolCreateInfo poolInfo = { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO };
  poolInfo.queueFamilyIndex = m_device->queues().graphics.queueFamily;
  poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
  VkResult status = m_vkd->vkCreateCommandPool(
      m_vkd->device(), &poolInfo, nullptr, &m_offscreenCmdPool);
  if (status) return status;

  uint32_t count = m_info.imageCount;
  m_offscreenStagingBuf.resize(count, VK_NULL_HANDLE);
  m_offscreenStagingMem.resize(count, VK_NULL_HANDLE);
  m_offscreenReadbackFence.resize(count, VK_NULL_HANDLE);

  VkDeviceSize stagingSize = VkDeviceSize(m_info.imageExtent.width)
                           * VkDeviceSize(m_info.imageExtent.height) * 4;

  for (uint32_t i = 0; i < count; i++) {
    VkBufferCreateInfo bufInfo = { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO };
    bufInfo.size = stagingSize;
    bufInfo.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    bufInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    status = m_vkd->vkCreateBuffer(m_vkd->device(), &bufInfo, nullptr,
        &m_offscreenStagingBuf[i]);
    if (status) return status;

    VkMemoryRequirements memReq;
    m_vkd->vkGetBufferMemoryRequirements(m_vkd->device(),
        m_offscreenStagingBuf[i], &memReq);

    VkMemoryAllocateInfo allocInfo = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO };
    allocInfo.allocationSize = memReq.size;
    allocInfo.memoryTypeIndex = m_device->findMemoryType(
        memReq.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT
            | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    status = m_vkd->vkAllocateMemory(m_vkd->device(), &allocInfo, nullptr,
        &m_offscreenStagingMem[i]);
    if (status) return status;

    status = m_vkd->vkBindBufferMemory(m_vkd->device(),
        m_offscreenStagingBuf[i], m_offscreenStagingMem[i], 0);
    if (status) return status;

    VkFenceCreateInfo fenceInfo = { VK_STRUCTURE_TYPE_FENCE_CREATE_INFO };
    fenceInfo.flags = VK_FENCE_CREATE_SIGNALED_BIT;
    status = m_vkd->vkCreateFence(m_vkd->device(), &fenceInfo, nullptr,
        &m_offscreenReadbackFence[i]);
    if (status) return status;
  }
  return VK_SUCCESS;
}
```

- [ ] **Step 3: Add destroyOffscreenReadback() implementation**

```cpp
void DxvkPresenter::destroyOffscreenReadback() {
  for (auto& fence : m_offscreenReadbackFence)
    if (fence) m_vkd->vkDestroyFence(m_vkd->device(), fence, nullptr);
  m_offscreenReadbackFence.clear();
  for (auto& mem : m_offscreenStagingMem)
    if (mem) m_vkd->vkFreeMemory(m_vkd->device(), mem, nullptr);
  m_offscreenStagingMem.clear();
  for (auto& buf : m_offscreenStagingBuf)
    if (buf) m_vkd->vkDestroyBuffer(m_vkd->device(), buf, nullptr);
  m_offscreenStagingBuf.clear();
  if (m_offscreenCmdPool)
    m_vkd->vkDestroyCommandPool(m_vkd->device(), m_offscreenCmdPool, nullptr);
  m_offscreenCmdPool = VK_NULL_HANDLE;
}
```

- [ ] **Step 4: Wire into recreateSwapchain**

After the existing offscreen image creation code (after the semaphore creation block), call `createOffscreenReadback()`. On failure, return the status.

In the cleanup block of recreateSwapchain (before the `} else {`), call `destroyOffscreenReadback()` after destroying image memory.

- [ ] **Step 5: Wire into destroySwapchain**

In the offscreen cleanup path, call `destroyOffscreenReadback()` after destroying memory.

- [ ] **Step 6: Build DXVK**

```bash
cd /tmp/dxvk-source-2.5.3/build-win64 && ninja -j4 2>&1 | tail -5
```

Expected: build succeeds with no errors.

- [ ] **Step 7: Commit the patch**

```bash
cd /tmp/dxvk-source-2.5.3 && git diff > /home/swong/dls/dxvk-offscreen-swapchain.patch
cd /home/swong/dls/gt-spector && git add -A && git commit -m "feat: DXVK readback infrastructure (staging buffers, fences, cmd pool)"
```

---

### Task 2: DXVK Presenter — Queue-Ordered Copy Submit + SHM Write

**Files:**
- Modify: `/tmp/dxvk-source-2.5.3/src/dxvk/dxvk_presenter.cpp` — `presentImage()`

**Interfaces:**
- Consumes: staging buffers, fences, command pool from Task 1
- Produces: `/dev/shm/gt-spector-<ID>-frame` with frame data

- [ ] **Step 1: Add SHM setup to createOffscreenReadback()**

In `createOffscreenReadback()`, after creating staging resources, open and map the SHM region:

```cpp
  // SHM
  char shmName[64];
  const char* shmId = getenv("GT_SPECTOR_SHM_ID");
  if (!shmId) shmId = "0";
  snprintf(shmName, sizeof(shmName), "/gt-spector-%s-frame", shmId);
  m_offscreenShmFd = shm_open(shmName, O_CREAT | O_RDWR, 0666);
  if (m_offscreenShmFd >= 0) {
    VkDeviceSize shmSize = stagingSize + 16; // header + pixels
    ftruncate(m_offscreenShmFd, shmSize);
    m_offscreenShmPtr = mmap(nullptr, shmSize, PROT_READ | PROT_WRITE,
        MAP_SHARED, m_offscreenShmFd, 0);
    m_offscreenShmSize = shmSize;
  }
```

Add these to the header:
```cpp
    int                       m_offscreenShmFd     = -1;
    void*                     m_offscreenShmPtr     = nullptr;
    VkDeviceSize              m_offscreenShmSize    = 0;
    uint64_t                  m_offscreenFrameCount = 0;
```

Add cleanup in `destroyOffscreenReadback()`:
```cpp
  if (m_offscreenShmPtr && m_offscreenShmPtr != MAP_FAILED)
    munmap(m_offscreenShmPtr, m_offscreenShmSize);
  if (m_offscreenShmFd >= 0) close(m_offscreenShmFd);
  m_offscreenShmPtr = nullptr;
  m_offscreenShmFd = -1;
```

Add includes at top of `dxvk_presenter.cpp`:
```cpp
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
```

- [ ] **Step 2: Implement readback in presentImage()**

Replace the current offscreen block in `presentImage()`:

```cpp
    if (m_offscreen) {
      // Queue-ordered copy readback
      if (m_offscreenCmdPool && m_offscreenReadbackFence.size() > m_imageIndex
          && m_offscreenReadbackFence[m_imageIndex] != VK_NULL_HANDLE
          && m_offscreenShmPtr) {
        // Wait for previous readback on this image to complete
        m_vkd->vkWaitForFences(m_vkd->device(), 1,
            &m_offscreenReadbackFence[m_imageIndex], VK_TRUE, UINT64_MAX);
        m_vkd->vkResetFences(m_vkd->device(), 1,
            &m_offscreenReadbackFence[m_imageIndex]);

        // Read back from staging buffer
        void* mapped = nullptr;
        if (m_vkd->vkMapMemory(m_vkd->device(),
            m_offscreenStagingMem[m_imageIndex], 0, VK_WHOLE_SIZE,
            0, &mapped) == VK_SUCCESS) {
          VkDeviceSize frameSize = VkDeviceSize(m_info.imageExtent.width)
                                 * VkDeviceSize(m_info.imageExtent.height) * 4;
          // Write header: frame_counter, width, height
          auto* header = reinterpret_cast<uint64_t*>(m_offscreenShmPtr);
          header[0] = m_offscreenFrameCount++;
          header[1] = m_info.imageExtent.width;
          header[2] = m_info.imageExtent.height;
          // Copy pixel data
          std::memcpy(header + 4, mapped, frameSize);
          m_vkd->vkUnmapMemory(m_vkd->device(),
              m_offscreenStagingMem[m_imageIndex]);
        }

        // Submit copy command buffer (queue-ordered, no waits)
        VkCommandBufferAllocateInfo allocInfo = {
            VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO };
        allocInfo.commandPool        = m_offscreenCmdPool;
        allocInfo.level              = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandBufferCount = 1;

        VkCommandBuffer cmdBuf;
        if (m_vkd->vkAllocateCommandBuffers(m_vkd->device(),
            &allocInfo, &cmdBuf) == VK_SUCCESS) {
          VkCommandBufferBeginInfo beginInfo = {
              VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
          beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;

          if (m_vkd->vkBeginCommandBuffer(cmdBuf, &beginInfo) == VK_SUCCESS) {
            VkBufferImageCopy region = {};
            region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
            region.imageSubresource.layerCount = 1;
            region.imageExtent.width  = m_info.imageExtent.width;
            region.imageExtent.height = m_info.imageExtent.height;
            region.imageExtent.depth  = 1;

            m_vkd->vkCmdCopyImageToBuffer(cmdBuf,
                m_images[m_imageIndex].image, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
                m_offscreenStagingBuf[m_imageIndex], 1, &region);
            m_vkd->vkEndCommandBuffer(cmdBuf);

            VkSubmitInfo submit = { VK_STRUCTURE_TYPE_SUBMIT_INFO };
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &cmdBuf;
            // No wait semaphores — queue ordering suffices

            m_vkd->vkQueueSubmit(m_device->queues().graphics.queueHandle,
                1, &submit, m_offscreenReadbackFence[m_imageIndex]);
          }
          m_vkd->vkFreeCommandBuffers(m_vkd->device(),
              m_offscreenCmdPool, 1, &cmdBuf);
        }
      }

      m_frameIndex += 1;
      m_frameIndex %= m_semaphores.size();
      return VK_SUCCESS;
    }
```

- [ ] **Step 3: Build DXVK**

```bash
cd /tmp/dxvk-source-2.5.3/build-win64 && ninja -j4 2>&1 | tail -5
```

Expected: build succeeds.

- [ ] **Step 4: Update patch file**

```bash
cd /tmp/dxvk-source-2.5.3 && git diff > /home/swong/dls/dxvk-offscreen-swapchain.patch
```

- [ ] **Step 5: Install DLLs and run test**

```bash
# Install
cp src/d3d11/d3d11.dll src/dxgi/dxgi.dll src/d3d10/d3d10core.dll \
  /home/swong/dls/wineprefix_dls/drive_c/windows/system32/

# Run game for 30s with SHM enabled
DISPLAY=:9 WINEPREFIX=/home/swong/dls/wineprefix_dls \
  WINEDLLOVERRIDES="d3d11=n;d3d10core=n;dxgi=n" DXVK_WSI_DRIVER=None \
  GT_SPECTOR_SHM_ID=9 \
  timeout 30 wine /home/swong/dls/wineprefix_dls/drive_c/Program\ Files/DoomsdayLastSurvivors/Doomsday_1.58.0/Doomsday.exe \
  -screen-width 1152 -screen-height 864 -popupwindow -logfile /tmp/dls-shm-test-$$.log 2>&1

# Verify SHM was created
ls -la /dev/shm/gt-spector-9-frame
```

Expected: SHM file exists with non-zero size (1152*864*4 = ~4MB + 16 bytes header).

- [ ] **Step 6: Commit**

```bash
cd /home/swong/dls/gt-spector && git add -A && git commit -m "feat: DXVK readback — queue-ordered copy submit and SHM write"
```

---

### Task 3: Python SHM Source

**Files:**
- Modify: `gt_spector/source.py` — use new SHM struct
- Modify: `gt_spector/screen.py` — add ShmScreen source

**Interfaces:**
- Consumes: SHM region at `/dev/shm/gt-spector-<N>-frame` from Task 2
- Produces: `Session` can now use `source="shm://9"` to read live frames

- [ ] **Step 1: Update source.py**

No changes needed — parse_source already handles `shm://` URIs. Good.

- [ ] **Step 2: Add ShmScreen to screen.py**

```python
import mmap
import struct
import numpy as np

class ShmScreen:
    def __init__(self, shm_id: str):
        self._path = f"/dev/shm/gt-spector-{shm_id}-frame"
        self._frame: np.ndarray | None = None
        self._last_counter = 0

    def refresh(self) -> np.ndarray:
        try:
            with open(self._path, "rb") as f:
                data = f.read(16)  # header
                if len(data) < 16:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                counter, w, h = struct.unpack("<QII", data)
                if counter == self._last_counter:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                self._last_counter = counter
                pixel_data = f.read(w * h * 4)
                if len(pixel_data) < w * h * 4:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                # BGRA → RGB numpy
                arr = np.frombuffer(pixel_data, dtype=np.uint8).reshape((h, w, 4))
                self._frame = arr[:, :, [2, 1, 0]].copy()  # BGRA → RGB
                return self._frame
        except FileNotFoundError:
            return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            return self.refresh()
        return self._frame

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return tuple(map(int, self.frame[y, x]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()
```

- [ ] **Step 3: Update session.py to use ShmScreen**

In `Session.__init__`, add the SHM case:

```python
        if spec.kind == SourceKind.FILE:
            self._screen = Screen(spec.path)
        elif spec.kind == SourceKind.SHM:
            from .screen import ShmScreen
            self._screen = ShmScreen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind} not implemented")
```

- [ ] **Step 4: Write test for ShmScreen**

```python
def test_shm_screen(tmp_path):
    from gt_spector.screen import ShmScreen
    import numpy as np
    import struct

    # Create a fake SHM file
    shm_path = str(tmp_path / "gt-spector-test-frame")
    w, h = 100, 50
    header = struct.pack("<QII", 1, w, h)
    pixels = b'\xff\x00\x00\xff' * (w * h)  # BGRA red
    with open(shm_path, "wb") as f:
        f.write(header + pixels)

    sc = ShmScreen.__new__(ShmScreen)
    sc._path = shm_path
    sc._frame = None
    sc._last_counter = 0

    frame = sc.refresh()
    assert frame.shape == (h, w, 3)
    assert tuple(frame[0, 0]) == (255, 0, 0)  # BGR→RGB: 0x00,0x00,0xFF → (255,0,0)
```

- [ ] **Step 5: Run tests**

```bash
cd /home/swong/dls/gt-spector && python3 -m pytest tests/ -v
```

Expected: all tests pass (including new ShmScreen test).

- [ ] **Step 6: Run viewer with SHM source**

```bash
# First, ensure the DXVK game ran and created /dev/shm/gt-spector-9-frame
# Then:
python3 -m gt_spector --session :9 --source shm://9
```

Note: This will error if the game hasn't created the SHM file yet. Test only after running the game with GT_SPECTOR_SHM_ID=9.

- [ ] **Step 7: Commit**

```bash
git add gt_spector/screen.py gt_spector/session.py tests/
git commit -m "feat: SHM source for live frame capture from DXVK readback"
```

---

### Task 4: End-to-End Verification

**Files:**
- Modify: `/tmp/dxvk-source-2.5.3/build-win64/` — rebuild
- Run: verification script

- [ ] **Step 1: Build and install DXVK**

```bash
cd /tmp/dxvk-source-2.5.3/build-win64 && ninja -j4
cp src/d3d11/d3d11.dll src/dxgi/dxgi.dll src/d3d10/d3d10core.dll \
  /home/swong/dls/wineprefix_dls/drive_c/windows/system32/
```

- [ ] **Step 2: Launch game with SHM on display :9**

```bash
rm -f /dev/shm/gt-spector-9-frame
DISPLAY=:9 WINEPREFIX=/home/swong/dls/wineprefix_dls \
  WINEDLLOVERRIDES="d3d11=n;d3d10core=n;dxgi=n" DXVK_WSI_DRIVER=None \
  GT_SPECTOR_SHM_ID=9 \
  timeout 60 wine /home/swong/dls/wineprefix_dls/drive_c/Program\ Files/DoomsdayLastSurvivors/Doomsday_1.58.0/Doomsday.exe \
  -screen-width 1152 -screen-height 864 -popupwindow -logfile /tmp/dls-e2e-$$.log &
GAME_PID=$!
sleep 15  # Let game warm up and render a few frames
```

- [ ] **Step 3: Launch viewer with SHM source**

```bash
DISPLAY=:0 python3 -m gt_spector --source shm://9 --session :9 &
VIEWER_PID=$!
sleep 5
kill $VIEWER_PID 2>/dev/null
kill $GAME_PID 2>/dev/null
```

Expected: viewer window opens on :0 showing a live game frame (not the test pattern).

- [ ] **Step 4: Final commit**

```bash
cd /home/swong/dls/gt-spector && git add -A && git commit -m "docs: end-to-end verification instructions"
cd /tmp/dxvk-source-2.5.3 && git diff > /home/swong/dls/dxvk-offscreen-swapchain.patch
```
