// probe_collect: calls read-only vendor getters in rounds to collect packets.
//
// Every call here is a getter; nothing is set on the camera. Each round asks
// for the same values, so the sequence number advances while the commands
// repeat, which gives the varied packets a checksum solve needs.
//
// Usage: probe_collect [rounds] [detect_wait_ms]
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include <dev/devs.hpp>

int main(int argc, char **argv) {
    int rounds = argc > 1 ? std::stoi(argv[1]) : 20;
    int wait_ms = argc > 2 ? std::stoi(argv[2]) : 8000;
    Devices::get().setEnableMdnsScan(false);
    std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));
    auto list = Devices::get().getDevList();
    if (list.empty()) { std::printf("[collect] no device\n"); return 1; }
    auto d = list.front();
    std::printf("[collect] product=%d version=%s\n", static_cast<int>(d->productType()), d->devVersion().c_str());

    for (int r = 0; r < rounds; r++) {
        int32_t i = 0; float f = 0; bool b = false;
        int rc;
        rc = d->cameraGetZoomAbsoluteR(f);       std::printf("[collect] r=%d zoom rc=%d v=%.3f\n", r, rc, f);
        rc = d->cameraGetWdrR(i);                std::printf("[collect] r=%d wdr rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetFaceAER(b);             std::printf("[collect] r=%d faceAE rc=%d v=%d\n", r, rc, b);
        rc = d->cameraGetAELockR(b);             std::printf("[collect] r=%d aeLock rc=%d v=%d\n", r, rc, b);
        rc = d->cameraGetExposureModeR(i);       std::printf("[collect] r=%d expMode rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetAntiFlickR(i);          std::printf("[collect] r=%d antiFlick rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetMirrorFlipR(i);         std::printf("[collect] r=%d mirrorFlip rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetImageBrightnessR(i);    std::printf("[collect] r=%d brightness rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetImageContrastR(i);      std::printf("[collect] r=%d contrast rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetImageHueR(i);           std::printf("[collect] r=%d hue rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetImageSaturationR(i);    std::printf("[collect] r=%d saturation rc=%d v=%d\n", r, rc, i);
        Device::UvcParamRange range{};
        rc = d->cameraGetRangeImageBrightnessR(range); std::printf("[collect] r=%d brightnessRange rc=%d\n", r, rc);
    }
    Devices::get().close();
    return 0;
}
