/* -*- Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil -*- */
/*
 * Copyright (c) 2012-2021 University of California, Los Angeles
 *
 * This file is part of ndn-svs, synchronization library for distributed realtime
 * applications for NDN.
 *
 * ndn-svs library is free software: you can redistribute it and/or modify it under the
 * terms of the GNU Lesser General Public License as published by the Free Software
 * Foundation, in version 2.1 of the License.
 *
 * ndn-svs library is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
 * PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.
 */

#include "syncps.h"

#include <thread>
#include <ndn-cxx/util/random.hpp>
#include <ndn-svs/store-memory.hpp>
#include <chrono>
#include <utility>
#include <vector>
#include <thread>
#include <string>
#include <iostream>

using namespace ndn::svs;
using namespace std::chrono_literals;

class SyncPSUaV {

public:
    explicit SyncPSUaV(ndn::Name syncPrefix)
            : m_running(true),
              m_syncPrefix(std::move(syncPrefix)) { // Size of voice publications between 12 and 20 bytes{

        instanciateSync();
    }

    void
    run() {
        std::thread thread_svs([this] { face.processEvents(); });

        thread_svs.join();
    }

    void instanciateSync() {
        std::cout << "Create syncps Instance" << std::endl;

        m_sync = std::make_shared<syncps::SyncPubsub>(
                face, m_syncPrefix, isExpired, filterPubs);
        m_sync->setSyncInterestLifetime(ndn::time::milliseconds(1000));
    }


    static inline const syncps::FilterPubsCb filterPubs =
            [](auto &pOurs, auto &pOthers) mutable {
                // Only reply if at least one of the pubs is ours. Order the
                // reply by ours/others then most recent first (to minimize latency).
                // Respond with as many pubs will fit in one Data.
                if (pOurs.empty()) {
                    return pOurs;
                }
                const auto cmp = [](const auto p1, const auto p2) {
                    ndn::time::system_clock::TimePoint tp1 = (p1->getName()[-1].isTimestamp())
                                                             ? p1->getName()[-1].toTimestamp()
                                                             : p1->getName()[-3].toTimestamp();
                    ndn::time::system_clock::TimePoint tp2 = (p2->getName()[-1].isTimestamp())
                                                             ? p2->getName()[-1].toTimestamp()
                                                             : p2->getName()[-3].toTimestamp();
                    return tp1 > tp2;
                };
                if (pOurs.size() > 1) {
                    std::sort(pOurs.begin(), pOurs.end(), cmp);
                }
                std::sort(pOthers.begin(), pOthers.end(), cmp);
                for (auto &p : pOthers) {
                    pOurs.push_back(p);
                }
                return pOurs;
            };

    static inline const syncps::IsExpiredCb isExpired =
            [](auto p) {
                if (p.getName()[-1].isTimestamp()) {
                    auto dt = ndn::time::system_clock::now() - p.getName()[-1].toTimestamp();
                    return dt >= syncps::maxPubLifetime + syncps::maxClockSkew || dt <= -syncps::maxClockSkew;
                } else {
                    auto dt = ndn::time::system_clock::now() - p.getName()[-3].toTimestamp();
                    return dt >= syncps::maxPubLifetime + syncps::maxClockSkew || dt <= -syncps::maxClockSkew;
                }
            };

protected:
    bool m_running;
    ndn::Name m_syncPrefix;
    ndn::Face face;
    ndn::security::SigningInfo m_signingInfo;
    ndn::KeyChain m_keyChain;
    ndn::svs::MemoryDataStore m_dataStore;
    std::shared_ptr<syncps::SyncPubsub> m_sync;

};

int main(int argc, char **argv) {
    ndn::Name syncPrefix("/ndn/svs");

    SyncPSUaV program(syncPrefix);
    program.run();
    return 0;
}
