// probe_collect_varied: calls read-only vendor getters whose replies vary in
// length and content (value ranges, lists, exposure settings), to collect
// replies for solving the payload check. Nothing is set on the camera.
//
// Usage: probe_collect_varied [rounds] [detect_wait_ms]
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>

#include <dev/devs.hpp>

int main(int argc, char **argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);  // unbuffered, so the shim timestamps each line when printed
    int rounds = argc > 1 ? std::stoi(argv[1]) : 3;
    int wait_ms = argc > 2 ? std::stoi(argv[2]) : 6000;
    Devices::get().setEnableMdnsScan(false);
    std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));
    auto list = Devices::get().getDevList();
    if (list.empty()) { std::printf("[varied] no device\n"); return 1; }
    auto d = list.front();
    std::printf("[varied] product=%d version=%s\n", static_cast<int>(d->productType()), d->devVersion().c_str());

    for (int r = 0; r < rounds; r++) {
        Device::UvcParamRange g{};
        int rc;
#define RANGE(fn) rc = d->fn(g); std::printf("[varied] r=%d %s rc=%d\n", r, #fn, rc);
        RANGE(cameraGetRangeZoomAbsoluteR)
        RANGE(cameraGetRangeWhiteBalanceR)
        RANGE(cameraGetRangePAEEvBiasR)
        RANGE(cameraGetRangeMAEIsoR)
        RANGE(cameraGetRangeAntiFlickR)
        RANGE(cameraGetRangeImageBrightnessR)
        RANGE(cameraGetRangeImageContrastR)
        RANGE(cameraGetRangeImageHueR)
        RANGE(cameraGetRangeImageSaturationR)
        RANGE(cameraGetRangeImageSharpR)
#undef RANGE
        std::vector<int32_t> v; int32_t mn = 0, mx = 0;
        rc = d->cameraGetWdrListR(v); std::printf("[varied] r=%d wdrList rc=%d n=%zu\n", r, rc, v.size());
        v.clear();
        rc = d->cameraGetWhiteBalanceListR(v, mn, mx); std::printf("[varied] r=%d wbList rc=%d n=%zu\n", r, rc, v.size());
        Device::WhiteBalanceSetting wb{};
        rc = d->cameraGetWhiteBalanceR(wb); std::printf("[varied] r=%d whiteBalance rc=%d\n", r, rc);
        uint32_t a = 0, b = 0;
        rc = d->cameraGetISOLimitR(a, b); std::printf("[varied] r=%d isoLimit rc=%d %u..%u\n", r, rc, a, b);
        int32_t i = 0;
        rc = d->cameraGetPAEEvBiasR(i);  std::printf("[varied] r=%d paeEvBias rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetSAEShutterR(i); std::printf("[varied] r=%d saeShutter rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetMAEShutterR(i); std::printf("[varied] r=%d maeShutter rc=%d v=%d\n", r, rc, i);
        rc = d->cameraGetMAEIsoR(i);     std::printf("[varied] r=%d maeIso rc=%d v=%d\n", r, rc, i);
        Device::DevAEEvBiasType ev{};
        rc = d->cameraGetAAEEvBiasR(ev); std::printf("[varied] r=%d aaeEvBias rc=%d v=%d\n", r, rc, static_cast<int>(ev));
    }
    Devices::get().close();
    return 0;
}
