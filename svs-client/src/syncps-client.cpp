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
#include "AbstractProgram.h"

using namespace ndn::svs;
using namespace std::chrono_literals;

class SVSProgram : public AbstractProgram {

public:
    SVSProgram(ndn::Name syncPrefix, ndn::Name participantPrefix)
            : AbstractProgram(syncPrefix, participantPrefix) {

        instanciateSync();
    }

    void instanciateSync() override {
        std::cout << "Create syncps Instance" << std::endl;

        m_sync = std::make_shared<syncps::SyncPubsub>(
                face, m_syncPrefix, isExpired, filterPubs);
        m_sync->setSyncInterestLifetime(ndn::time::milliseconds(1000));

        m_sync->subscribeTo(
                ndn::Name("/position"),
                [&](const syncps::Publication &publication) {
                    // Todo: Log received Data
                    const unsigned long data_size = publication.getContent().value_size();
                    const std::basic_string<char> content_str((char *) publication.getContent().value(), data_size);

                    std::cout << "Got Data: " << publication.getName()
                              << std::endl;

                    BOOST_LOG_TRIVIAL(info) << "RECV_MSG::" << publication.getName().toUri();
                }
        );

        m_sync->subscribeTo(
                ndn::Name("/voice").append(m_platoonPrefix),
                [&](const syncps::Publication &publication) {
                    // Todo: Log received Data
                    const unsigned long data_size = publication.getContent().value_size();
                    const std::basic_string<char> content_str((char *) publication.getContent().value(), data_size);
                    int segments = publication.getFinalBlock()->toNumber();

                    std::cout << "Got Data: " << publication.getName() << ", fetch " << segments << " segments"
                              << std::endl;
                    BOOST_LOG_TRIVIAL(info) << "RECV_MSG::" << publication.getName().toUri();

                    fetchOutStandingVoiceSegements(publication.getName(), segments);
                }
        );
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

    void publishData(const ndn::Data &data) override {
        syncps::Publication pub(data);
        m_sync->publish(std::move(pub));
    }

protected:
    std::shared_ptr<syncps::SyncPubsub> m_sync;

};

int main(int argc, char **argv) {
    if (argc != 3) {
        std::cout << "Usage: client <prefix> <logfile>" << std::endl;
        exit(1);
    }

    ndn::Name syncPrefix("/ndn/svs");
    ndn::Name participantPrefix(argv[1]);

    initlogger(argv[2]);

    SVSProgram program(syncPrefix, participantPrefix);
    program.run();
    return 0;
}
