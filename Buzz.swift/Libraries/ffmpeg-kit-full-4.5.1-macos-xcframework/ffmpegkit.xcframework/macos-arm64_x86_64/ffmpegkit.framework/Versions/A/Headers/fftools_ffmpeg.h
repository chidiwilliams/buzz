/*
 * This file is part of FFmpeg.
 *
 * FFmpeg is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * FFmpeg is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with FFmpeg; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

/*
 * CHANGES 06.2020
 * - cancel_operation() method signature updated with id
 *
 * CHANGES 01.2020
 * - ffprobe support changes
 *
 * CHANGES 12.2019
 * - Concurrent execution support
 *
 * CHANGES 03.2019
 * --------------------------------------------------------
 * - config.h include removed
 *
 * CHANGES 08.2018
 * --------------------------------------------------------
 * - fftools_ prefix added to file name and include guards
 * - set_report_callback() method declared
 * - cancel_operation() method declared
 *
 * CHANGES 07.2018
 * --------------------------------------------------------
 * - Include guards renamed
 */

#ifndef FFTOOLS_FFMPEG_H
#define FFTOOLS_FFMPEG_H

#include <stdint.h>
#include <stdio.h>
#include <signal.h>

#include "fftools_cmdutils.h"

#include "libavformat/avformat.h"
#include "libavformat/avio.h"

#include "libavcodec/avcodec.h"
#include "libavcodec/bsf.h"

#include "libavfilter/avfilter.h"

#include "libavutil/avutil.h"
#include "libavutil/dict.h"
#include "libavutil/eval.h"
#include "libavutil/fifo.h"
#include "libavutil/hwcontext.h"
#include "libavutil/pixfmt.h"
#include "libavutil/rational.h"
#include "libavutil/thread.h"
#include "libavutil/threadmessage.h"

#include "libswresample/swresample.h"

#define VSYNC_AUTO       -1
#define VSYNC_PASSTHROUGH 0
#define VSYNC_CFR         1
#define VSYNC_VFR         2
#define VSYNC_VSCFR       0xfe
#define VSYNC_DROP        0xff

#define MAX_STREAMS 1024    /* arbitrary sanity check value */

enum HWAccelID {
    HWACCEL_NONE = 0,
    HWACCEL_AUTO,
    HWACCEL_GENERIC,
    HWACCEL_VIDEOTOOLBOX,
};

typedef struct HWAccel {
    const char *name;
    int (*init)(AVCodecContext *s);
    enum HWAccelID id;
    enum AVPixelFormat pix_fmt;
} HWAccel;

typedef struct HWDevice {
    const char *name;
    enum AVHWDeviceType type;
    AVBufferRef *device_ref;
} HWDevice;

/* select an input stream for an output stream */
typedef struct StreamMap {
    int disabled;           /* 1 is this mapping is disabled by a negative map */
    int file_index;
    int stream_index;
    int sync_file_index;
    int sync_stream_index;
    char *linklabel;       /* name of an output link, for mapping lavfi outputs */
} StreamMap;

typedef struct {
    int  file_idx,  stream_idx,  channel_idx; // input
    int ofile_idx, ostream_idx;               // output
} AudioChannelMap;

typedef struct OptionsContext {
    OptionGroup *g;

    /* input/output options */
    int64_t start_time;
    int64_t start_time_eof;
    int seek_timestamp;
    const char *format;

    SpecifierOpt *codec_names;
    int        nb_codec_names;
    SpecifierOpt *audio_channels;
    int        nb_audio_channels;
    SpecifierOpt *audio_sample_rate;
    int        nb_audio_sample_rate;
    SpecifierOpt *frame_rates;
    int        nb_frame_rates;
    SpecifierOpt *max_frame_rates;
    int        nb_max_frame_rates;
    SpecifierOpt *frame_sizes;
    int        nb_frame_sizes;
    SpecifierOpt *frame_pix_fmts;
    int        nb_frame_pix_fmts;

    /* input options */
    int64_t input_ts_offset;
    int loop;
    int rate_emu;
    float readrate;
    int accurate_seek;
    int thread_queue_size;

    SpecifierOpt *ts_scale;
    int        nb_ts_scale;
    SpecifierOpt *dump_attachment;
    int        nb_dump_attachment;
    SpecifierOpt *hwaccels;
    int        nb_hwaccels;
    SpecifierOpt *hwaccel_devices;
    int        nb_hwaccel_devices;
    SpecifierOpt *hwaccel_output_formats;
    int        nb_hwaccel_output_formats;
    SpecifierOpt *autorotate;
    int        nb_autorotate;

    /* output options */
    StreamMap *stream_maps;
    int     nb_stream_maps;
    AudioChannelMap *audio_channel_maps; /* one info entry per -map_channel */
    int           nb_audio_channel_maps; /* number of (valid) -map_channel settings */
    int metadata_global_manual;
    int metadata_streams_manual;
    int metadata_chapters_manual;
    const char **attachments;
    int       nb_attachments;

    int chapters_input_file;

    int64_t recording_time;
    int64_t stop_time;
    uint64_t limit_filesize;
    float mux_preload;
    float mux_max_delay;
    int shortest;
    int bitexact;

    int video_disable;
    int audio_disable;
    int subtitle_disable;
    int data_disable;

    /* indexed by output file stream index */
    int   *streamid_map;
    int nb_streamid_map;

    SpecifierOpt *metadata;
    int        nb_metadata;
    SpecifierOpt *max_frames;
    int        nb_max_frames;
    SpecifierOpt *bitstream_filters;
    int        nb_bitstream_filters;
    SpecifierOpt *codec_tags;
    int        nb_codec_tags;
    SpecifierOpt *sample_fmts;
    int        nb_sample_fmts;
    SpecifierOpt *qscale;
    int        nb_qscale;
    SpecifierOpt *forced_key_frames;
    int        nb_forced_key_frames;
    SpecifierOpt *force_fps;
    int        nb_force_fps;
    SpecifierOpt *frame_aspect_ratios;
    int        nb_frame_aspect_ratios;
    SpecifierOpt *rc_overrides;
    int        nb_rc_overrides;
    SpecifierOpt *intra_matrices;
    int        nb_intra_matrices;
    SpecifierOpt *inter_matrices;
    int        nb_inter_matrices;
    SpecifierOpt *chroma_intra_matrices;
    int        nb_chroma_intra_matrices;
    SpecifierOpt *top_field_first;
    int        nb_top_field_first;
    SpecifierOpt *metadata_map;
    int        nb_metadata_map;
    SpecifierOpt *presets;
    int        nb_presets;
    SpecifierOpt *copy_initial_nonkeyframes;
    int        nb_copy_initial_nonkeyframes;
    SpecifierOpt *copy_prior_start;
    int        nb_copy_prior_start;
    SpecifierOpt *filters;
    int        nb_filters;
    SpecifierOpt *filter_scripts;
    int        nb_filter_scripts;
    SpecifierOpt *reinit_filters;
    int        nb_reinit_filters;
    SpecifierOpt *fix_sub_duration;
    int        nb_fix_sub_duration;
    SpecifierOpt *canvas_sizes;
    int        nb_canvas_sizes;
    SpecifierOpt *pass;
    int        nb_pass;
    SpecifierOpt *passlogfiles;
    int        nb_passlogfiles;
    SpecifierOpt *max_muxing_queue_size;
    int        nb_max_muxing_queue_size;
    SpecifierOpt *muxing_queue_data_threshold;
    int        nb_muxing_queue_data_threshold;
    SpecifierOpt *guess_layout_max;
    int        nb_guess_layout_max;
    SpecifierOpt *apad;
    int        nb_apad;
    SpecifierOpt *discard;
    int        nb_discard;
    SpecifierOpt *disposition;
    int        nb_disposition;
    SpecifierOpt *program;
    int        nb_program;
    SpecifierOpt *time_bases;
    int        nb_time_bases;
    SpecifierOpt *enc_time_bases;
    int        nb_enc_time_bases;
    SpecifierOpt *autoscale;
    int        nb_autoscale;
} OptionsContext;

typedef struct InputFilter {
    AVFilterContext    *filter;
    struct InputStream *ist;
    struct FilterGraph *graph;
    uint8_t            *name;
    enum AVMediaType    type;   // AVMEDIA_TYPE_SUBTITLE for sub2video

    AVFifoBuffer *frame_queue;

    // parameters configured for this input
    int format;

    int width, height;
    AVRational sample_aspect_ratio;

    int sample_rate;
    int channels;
    uint64_t channel_layout;

    AVBufferRef *hw_frames_ctx;

    int eof;
} InputFilter;

typedef struct OutputFilter {
    AVFilterContext     *filter;
    struct OutputStream *ost;
    struct FilterGraph  *graph;
    uint8_t             *name;

    /* temporary storage until stream maps are processed */
    AVFilterInOut       *out_tmp;
    enum AVMediaType     type;

    /* desired output stream properties */
    int width, height;
    AVRational frame_rate;
    int format;
    int sample_rate;
    uint64_t channel_layout;

    // those are only set if no format is specified and the encoder gives us multiple options
    int *formats;
    uint64_t *channel_layouts;
    int *sample_rates;
} OutputFilter;

typedef struct FilterGraph {
    int            index;
    const char    *graph_desc;

    AVFilterGraph *graph;
    int reconfiguration;

    InputFilter   **inputs;
    int          nb_inputs;
    OutputFilter **outputs;
    int         nb_outputs;
} FilterGraph;

typedef struct InputStream {
    int file_index;
    AVStream *st;
    int discard;             /* true if stream data should be discarded */
    int user_set_discard;
    int decoding_needed;     /* non zero if the packets must be decoded in 'raw_fifo', see DECODING_FOR_* */
#define DECODING_FOR_OST    1
#define DECODING_FOR_FILTER 2

    AVCodecContext *dec_ctx;
    const AVCodec *dec;
    AVFrame *decoded_frame;
    AVFrame *filter_frame; /* a ref of decoded_frame, to be sent to filters */
    AVPacket *pkt;

    int64_t       start;     /* time when read started */
    /* predicted dts of the next packet read for this stream or (when there are
     * several frames in a packet) of the next frame in current packet (in AV_TIME_BASE units) */
    int64_t       next_dts;
    int64_t first_dts;       ///< dts of the first packet read for this stream (in AV_TIME_BASE units)
    int64_t       dts;       ///< dts of the last packet read for this stream (in AV_TIME_BASE units)

    int64_t       next_pts;  ///< synthetic pts for the next decode frame (in AV_TIME_BASE units)
    int64_t       pts;       ///< current pts of the decoded frame  (in AV_TIME_BASE units)
    int           wrap_correction_done;

    int64_t filter_in_rescale_delta_last;

    int64_t min_pts; /* pts with the smallest value in a current stream */
    int64_t max_pts; /* pts with the higher value in a current stream */

    // when forcing constant input framerate through -r,
    // this contains the pts that will be given to the next decoded frame
    int64_t cfr_next_pts;

    int64_t nb_samples; /* number of samples in the last decoded audio frame before looping */

    double ts_scale;
    int saw_first_ts;
    AVDictionary *decoder_opts;
    AVRational framerate;               /* framerate forced with -r */
    int top_field_first;
    int guess_layout_max;

    int autorotate;

    int fix_sub_duration;
    struct { /* previous decoded subtitle and related variables */
        int got_output;
        int ret;
        AVSubtitle subtitle;
    } prev_sub;

    struct sub2video {
        int64_t last_pts;
        int64_t end_pts;
        AVFifoBuffer *sub_queue;    ///< queue of AVSubtitle* before filter init
        AVFrame *frame;
        int w, h;
        unsigned int initialize; ///< marks if sub2video_update should force an initialization
    } sub2video;

    int dr1;

    /* decoded data from this stream goes into all those filters
     * currently video and audio only */
    InputFilter **filters;
    int        nb_filters;

    int reinit_filters;

    /* hwaccel options */
    enum HWAccelID hwaccel_id;
    enum AVHWDeviceType hwaccel_device_type;
    char  *hwaccel_device;
    enum AVPixelFormat hwaccel_output_format;

    /* hwaccel context */
    void  *hwaccel_ctx;
    void (*hwaccel_uninit)(AVCodecContext *s);
    int  (*hwaccel_get_buffer)(AVCodecContext *s, AVFrame *frame, int flags);
    int  (*hwaccel_retrieve_data)(AVCodecContext *s, AVFrame *frame);
    enum AVPixelFormat hwaccel_pix_fmt;
    enum AVPixelFormat hwaccel_retrieved_pix_fmt;
    AVBufferRef *hw_frames_ctx;

    /* stats */
    // combined size of all the packets read
    uint64_t data_size;
    /* number of packets successfully read for this stream */
    uint64_t nb_packets;
    // number of frames/samples retrieved from the decoder
    uint64_t frames_decoded;
    uint64_t samples_decoded;

    int64_t *dts_buffer;
    int nb_dts_buffer;

    int got_output;
} InputStream;

typedef struct InputFile {
    AVFormatContext *ctx;
    int eof_reached;      /* true if eof reached */
    int eagain;           /* true if last read attempt returned EAGAIN */
    int ist_index;        /* index of first stream in input_streams */
    int loop;             /* set number of times input stream should be looped */
    int64_t duration;     /* actual duration of the longest stream in a file
                             at the moment when looping happens */
    AVRational time_base; /* time base of the duration */
    int64_t input_ts_offset;

    int64_t ts_offset;
    int64_t last_ts;
    int64_t start_time;   /* user-specified start time in AV_TIME_BASE or AV_NOPTS_VALUE */
    int seek_timestamp;
    int64_t recording_time;
    int nb_streams;       /* number of stream that ffmpeg is aware of; may be different
                             from ctx.nb_streams if new streams appear during av_read_frame() */
    int nb_streams_warn;  /* number of streams that the user was warned of */
    int rate_emu;
    float readrate;
    int accurate_seek;

    AVPacket *pkt;

#if HAVE_THREADS
    AVThreadMessageQueue *in_thread_queue;
    pthread_t thread;           /* thread reading from this file */
    int non_blocking;           /* reading packets from the thread should not block */
    int joined;                 /* the thread has been joined */
    int thread_queue_size;      /* maximum number of queued packets */
#endif
} InputFile;

enum forced_keyframes_const {
    FKF_N,
    FKF_N_FORCED,
    FKF_PREV_FORCED_N,
    FKF_PREV_FORCED_T,
    FKF_T,
    FKF_NB
};

#define ABORT_ON_FLAG_EMPTY_OUTPUT (1 <<  0)
#define ABORT_ON_FLAG_EMPTY_OUTPUT_STREAM (1 <<  1)

extern const char *const forced_keyframes_const_names[];

typedef enum {
    ENCODER_FINISHED = 1,
    MUXER_FINISHED = 2,
} OSTFinished ;

typedef struct OutputStream {
    int file_index;          /* file index */
    int index;               /* stream index in the output file */
    int source_index;        /* InputStream index */
    AVStream *st;            /* stream in the output file */
    int encoding_needed;     /* true if encoding needed for this stream */
    int frame_number;
    /* input pts and corresponding output pts
       for A/V sync */
    struct InputStream *sync_ist; /* input stream to sync against */
    int64_t sync_opts;       /* output frame counter, could be changed to some true timestamp */ // FIXME look at frame_number
    /* pts of the first frame encoded for this stream, used for limiting
     * recording time */
    int64_t first_pts;
    /* dts of the last packet sent to the muxer */
    int64_t last_mux_dts;
    // the timebase of the packets sent to the muxer
    AVRational mux_timebase;
    AVRational enc_timebase;

    AVBSFContext            *bsf_ctx;

    AVCodecContext *enc_ctx;
    AVCodecParameters *ref_par; /* associated input codec parameters with encoders options applied */
    const AVCodec *enc;
    int64_t max_frames;
    AVFrame *filtered_frame;
    AVFrame *last_frame;
    AVPacket *pkt;
    int last_dropped;
    int last_nb0_frames[3];

    void  *hwaccel_ctx;

    /* video only */
    AVRational frame_rate;
    AVRational max_frame_rate;
    int is_cfr;
    int force_fps;
    int top_field_first;
    int rotate_overridden;
    int autoscale;
    double rotate_override_value;

    AVRational frame_aspect_ratio;

    /* forced key frames */
    int64_t forced_kf_ref_pts;
    int64_t *forced_kf_pts;
    int forced_kf_count;
    int forced_kf_index;
    char *forced_keyframes;
    AVExpr *forced_keyframes_pexpr;
    double forced_keyframes_expr_const_values[FKF_NB];
    int dropped_keyframe;

    /* audio only */
    int *audio_channels_map;             /* list of the channels id to pick from the source stream */
    int audio_channels_mapped;           /* number of channels in audio_channels_map */

    char *logfile_prefix;
    FILE *logfile;

    OutputFilter *filter;
    char *avfilter;
    char *filters;         ///< filtergraph associated to the -filter option
    char *filters_script;  ///< filtergraph script associated to the -filter_script option

    AVDictionary *encoder_opts;
    AVDictionary *sws_dict;
    AVDictionary *swr_opts;
    AVDictionary *resample_opts;
    char *apad;
    OSTFinished finished;        /* no more packets should be written for this stream */
    int unavailable;                     /* true if the steram is unavailable (possibly temporarily) */
    int stream_copy;

    // init_output_stream() has been called for this stream
    // The encoder and the bitstream filters have been initialized and the stream
    // parameters are set in the AVStream.
    int initialized;

    int inputs_done;

    const char *attachment_filename;
    int copy_initial_nonkeyframes;
    int copy_prior_start;
    char *disposition;

    int keep_pix_fmt;

    /* stats */
    // combined size of all the packets written
    uint64_t data_size;
    // number of packets send to the muxer
    uint64_t packets_written;
    // number of frames/samples sent to the encoder
    uint64_t frames_encoded;
    uint64_t samples_encoded;

    /* packet quality factor */
    int quality;

    int max_muxing_queue_size;

    /* the packets are buffered here until the muxer is ready to be initialized */
    AVFifoBuffer *muxing_queue;

    /*
     * The size of the AVPackets' buffers in queue.
     * Updated when a packet is either pushed or pulled from the queue.
     */
    size_t muxing_queue_data_size;

    /* Threshold after which max_muxing_queue_size will be in effect */
    size_t muxing_queue_data_threshold;

    /* packet picture type */
    int pict_type;

    /* frame encode sum of squared error values */
    int64_t error[4];
} OutputStream;

typedef struct OutputFile {
    AVFormatContext *ctx;
    AVDictionary *opts;
    int ost_index;       /* index of the first stream in output_streams */
    int64_t recording_time;  ///< desired length of the resulting file in microseconds == AV_TIME_BASE units
    int64_t start_time;      ///< start time in microseconds == AV_TIME_BASE units
    uint64_t limit_filesize; /* filesize limit expressed in bytes */

    int shortest;

    int header_written;
} OutputFile;

extern __thread InputStream **input_streams;
extern __thread int        nb_input_streams;
extern __thread InputFile   **input_files;
extern __thread int        nb_input_files;

extern __thread OutputStream **output_streams;
extern __thread int         nb_output_streams;
extern __thread OutputFile   **output_files;
extern __thread int         nb_output_files;

extern __thread FilterGraph **filtergraphs;
extern __thread int        nb_filtergraphs;

extern __thread char *vstats_filename;
extern __thread char *sdp_filename;

extern __thread float audio_drift_threshold;
extern __thread float dts_delta_threshold;
extern __thread float dts_error_threshold;

extern __thread int audio_volume;
extern __thread int audio_sync_method;
extern __thread int video_sync_method;
extern __thread float frame_drop_threshold;
extern __thread int do_benchmark;
extern __thread int do_benchmark_all;
extern __thread int do_deinterlace;
extern __thread int do_hex_dump;
extern __thread int do_pkt_dump;
extern __thread int copy_ts;
extern __thread int start_at_zero;
extern __thread int copy_tb;
extern __thread int debug_ts;
extern __thread int exit_on_error;
extern __thread int abort_on_flags;
extern __thread int print_stats;
extern __thread int64_t stats_period;
extern __thread int qp_hist;
extern __thread int stdin_interaction;
extern __thread int frame_bits_per_raw_sample;
extern __thread AVIOContext *progress_avio;
extern __thread float max_error_rate;
extern __thread char *videotoolbox_pixfmt;

extern __thread int filter_nbthreads;
extern __thread int filter_complex_nbthreads;
extern __thread int vstats_version;
extern __thread int auto_conversion_filters;

extern __thread const AVIOInterruptCB int_cb;

extern const HWAccel hwaccels[];
#if CONFIG_QSV
extern __thread char *qsv_device;
#endif
extern __thread HWDevice *filter_hw_device;

void term_init(void);
void term_exit(void);

void reset_options(OptionsContext *o, int is_input);
void show_usage(void);

void opt_output_file(void *optctx, const char *filename);

void remove_avoptions(AVDictionary **a, AVDictionary *b);
void assert_avoptions(AVDictionary *m);

int guess_input_channel_layout(InputStream *ist);

enum AVPixelFormat choose_pixel_fmt(AVStream *st, AVCodecContext *avctx, const AVCodec *codec, enum AVPixelFormat target);
void choose_sample_fmt(AVStream *st, const AVCodec *codec);

int configure_filtergraph(FilterGraph *fg);
int configure_output_filter(FilterGraph *fg, OutputFilter *ofilter, AVFilterInOut *out);
void check_filter_outputs(void);
int ist_in_filtergraph(FilterGraph *fg, InputStream *ist);
int filtergraph_is_simple(FilterGraph *fg);
int init_simple_filtergraph(InputStream *ist, OutputStream *ost);
int init_complex_filtergraph(FilterGraph *fg);

void sub2video_update(InputStream *ist, int64_t heartbeat_pts, AVSubtitle *sub);

int ifilter_parameters_from_frame(InputFilter *ifilter, const AVFrame *frame);

int ffmpeg_parse_options(int argc, char **argv);

int videotoolbox_init(AVCodecContext *s);
int qsv_init(AVCodecContext *s);

HWDevice *hw_device_get_by_name(const char *name);
int hw_device_init_from_string(const char *arg, HWDevice **dev);
void hw_device_free_all(void);

int hw_device_setup_for_decode(InputStream *ist);
int hw_device_setup_for_encode(OutputStream *ost);
int hw_device_setup_for_filter(FilterGraph *fg);

int hwaccel_decode_init(AVCodecContext *avctx);

void set_report_callback(void (*callback)(int, float, float, int64_t, int, double, double));

void cancel_operation(long id);

int opt_map(void *optctx, const char *opt, const char *arg);
int opt_map_channel(void *optctx, const char *opt, const char *arg);
int opt_recording_timestamp(void *optctx, const char *opt, const char *arg);
int opt_data_frames(void *optctx, const char *opt, const char *arg);
int opt_progress(void *optctx, const char *opt, const char *arg);
int opt_target(void *optctx, const char *opt, const char *arg);
int opt_vsync(void *optctx, const char *opt, const char *arg);
int opt_abort_on(void *optctx, const char *opt, const char *arg);
int opt_stats_period(void *optctx, const char *opt, const char *arg);
int opt_qscale(void *optctx, const char *opt, const char *arg);
int opt_profile(void *optctx, const char *opt, const char *arg);
int opt_filter_complex(void *optctx, const char *opt, const char *arg);
int opt_filter_complex_script(void *optctx, const char *opt, const char *arg);
int opt_attach(void *optctx, const char *opt, const char *arg);
int opt_video_frames(void *optctx, const char *opt, const char *arg);
int opt_video_codec(void *optctx, const char *opt, const char *arg);
int opt_sameq(void *optctx, const char *opt, const char *arg);
int opt_timecode(void *optctx, const char *opt, const char *arg);

int opt_vstats_file(void *optctx, const char *opt, const char *arg);
int opt_vstats(void *optctx, const char *opt, const char *arg);
int opt_video_frames(void *optctx, const char *opt, const char *arg);
int opt_old2new(void *optctx, const char *opt, const char *arg);
int opt_streamid(void *optctx, const char *opt, const char *arg);
int opt_bitrate(void *optctx, const char *opt, const char *arg);
int show_hwaccels(void *optctx, const char *opt, const char *arg);
int opt_video_filters(void *optctx, const char *opt, const char *arg);
int opt_audio_frames(void *optctx, const char *opt, const char *arg);
int opt_audio_qscale(void *optctx, const char *opt, const char *arg);
int opt_audio_codec(void *optctx, const char *opt, const char *arg);
int opt_channel_layout(void *optctx, const char *opt, const char *arg);
int opt_preset(void *optctx, const char *opt, const char *arg);
int opt_audio_filters(void *optctx, const char *opt, const char *arg);
int opt_subtitle_codec(void *optctx, const char *opt, const char *arg);
int opt_video_channel(void *optctx, const char *opt, const char *arg);
int opt_video_standard(void *optctx, const char *opt, const char *arg);
int opt_sdp_file(void *optctx, const char *opt, const char *arg);
int opt_data_codec(void *optctx, const char *opt, const char *arg);
int opt_init_hw_device(void *optctx, const char *opt, const char *arg);
int opt_filter_hw_device(void *optctx, const char *opt, const char *arg);
void add_input_streams(OptionsContext *o, AVFormatContext *ic);
void assert_file_overwrite(const char *filename);
void dump_attachment(AVStream *st, const char *filename);
uint8_t *get_line(AVIOContext *s);
void uninit_options(OptionsContext *o);
void init_options(OptionsContext *o);
AVDictionary *strip_specifiers(AVDictionary *dict);
void parse_meta_type(char *arg, char *type, int *index, const char **stream_spec);
int fftools_copy_metadata(char *outspec, char *inspec, AVFormatContext *oc, AVFormatContext *ic, OptionsContext *o);
const AVCodec *find_codec_or_die(const char *name, enum AVMediaType type, int encoder);
const AVCodec *choose_decoder(OptionsContext *o, AVFormatContext *s, AVStream *st);
int open_input_file(OptionsContext *o, const char *filename);
int get_preset_file_2(const char *preset_name, const char *codec_name, AVIOContext **s);
int choose_encoder(OptionsContext *o, AVFormatContext *s, OutputStream *ost);
OutputStream *new_output_stream(OptionsContext *o, AVFormatContext *oc, enum AVMediaType type, int source_index);
void parse_matrix_coeffs(uint16_t *dest, const char *str);
uint8_t *fftools_read_file(const char *filename);
char *get_ost_filters(OptionsContext *o, AVFormatContext *oc, OutputStream *ost);
void check_streamcopy_filters(OptionsContext *o, AVFormatContext *oc, const OutputStream *ost, enum AVMediaType type);
OutputStream *new_video_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
OutputStream *new_audio_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
OutputStream *new_data_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
OutputStream *new_unknown_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
OutputStream *new_attachment_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
OutputStream *new_subtitle_stream(OptionsContext *o, AVFormatContext *oc, int source_index);
int copy_chapters(InputFile *ifile, OutputFile *ofile, int copy_metadata);
void init_output_filter(OutputFilter *ofilter, OptionsContext *o, AVFormatContext *oc);
int init_complex_filters(void);
int open_output_file(OptionsContext *o, const char *filename);
int opt_default_new(OptionsContext *o, const char *opt, const char *arg);
int open_files(OptionGroupList *l, const char *inout, int (*open_file)(OptionsContext*, const char*));

#endif /* FFTOOLS_FFMPEG_H */
