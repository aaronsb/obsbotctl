// probe_readonly: asks the vendor library for a camera's identity and status.
//
// It only calls getters (device list, name, version, product type, video
// node, cameraStatus). It sets nothing. The serial number is printed with
// all but its last four characters masked.
//
// Build against a pinned SDK in the local store, for example:
//   S=~/.local/share/libobsbot/sdk/libdev_v2.1.0_8
//   g++ -std=c++17 -O1 -I$S/include probe_readonly.cpp -L$S/lib -ldev -Wl,-rpath,$S/lib -o probe_readonly
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include <dev/devs.hpp>

static std::string mask(const std::string &s) {
    if (s.size() <= 4) return std::string(s.size(), '*');
    return std::string(s.size() - 4, '*') + s.substr(s.size() - 4);
}

int main(int argc, char **argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);  // unbuffered, so the shim timestamps each line when printed
    int wait_ms = argc > 1 ? std::stoi(argv[1]) : 8000;
    Devices::get().setDevChangedCallback(
        [](std::string sn, bool connected, void *) {
            std::printf("[probe] device %s %s\n", mask(sn).c_str(), connected ? "connected" : "disconnected");
        },
        nullptr);
    Devices::get().setEnableMdnsScan(false);
    std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));

    auto list = Devices::get().getDevList();
    std::printf("[probe] %zu device(s)\n", list.size());
    for (auto &d : list) {
        std::printf("[probe] sn=%s name=%s version=%s productType=%d video=%s\n",
                    mask(d->devSn()).c_str(), d->devName().c_str(), d->devVersion().c_str(),
                    static_cast<int>(d->productType()), d->videoDevPath().c_str());
        std::printf("[probe] marker: cameraStatus begin\n");
        auto st = d->cameraStatus();
        std::printf("[probe] marker: cameraStatus end\n");
        auto &t = st.tiny;
        std::printf("[probe] status dev_status=%u ai_mode=%u ai_sub_mode=%u zoom_ratio=%u hdr=%u face_ae=%u "
                    "auto_focus=%u manual_focus_value=%u fov=%u face_auto_focus=%u audio_auto_gain=%u ai_tracker_speed=%u\n",
                    t.dev_status, t.ai_mode, t.ai_sub_mode, t.zoom_ratio, t.hdr, t.face_ae, t.auto_focus,
                    t.manual_focus_value, t.fov, t.face_auto_focus, t.audio_auto_gain, t.ai_tracker_speed);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    Devices::get().close();
    return 0;
}
